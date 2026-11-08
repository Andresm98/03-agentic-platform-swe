#!/usr/bin/env python3
"""Reglas del flujo de ejercicios de la rama stage.

Solo usa la biblioteca estándar porque corre en el runner antes de instalar nada.

  check                                 valida todas las carpetas de exercises/
  plan --base A --head B [--scope]      valida y calcula qué publicar o retirar
  render NOMBRE --sha S --out-dir D     genera los values de Helm de un ejercicio
  sync --changed J --removed J --sha S --out-dir D

Los values los genera siempre CI. El estudiante solo controla exercise.yaml, así que no puede
pedir más recursos ni abrir salida de red.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXERCISES = ROOT / "exercises"
MAX_EXERCISES = 3
MAX_BYTES = 2 * 1024 * 1024
REGISTRY = "ghcr.io/andresm98/agentic-platform/exercises"
MIDDLEWARES = ",".join(
    f"traefik-{name}@kubernetescrd"
    for name in ("rate-limit", "body-limit", "strip-exercise-prefix")
)
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,29}[a-z0-9]$")
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40
REQUIRED_FILES = ("Dockerfile", "exercise.yaml", "README.md")
FORBIDDEN_NAMES = re.compile(r"^(\.env.*|.*\.pem|.*\.key|id_rsa.*)$")
CONFIG_KEYS = {"owner", "port", "description"}


class ExerciseError(Exception):
    """Incumplimiento de las reglas que debe ver el estudiante."""


def is_template(name: str) -> bool:
    return name.startswith("_")


def list_dirs(base: Path = EXERCISES) -> list[str]:
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def public_exercises(base: Path = EXERCISES) -> list[str]:
    return [name for name in list_dirs(base) if not is_template(name)]


def parse_config(path: Path) -> dict[str, str]:
    """Lee un YAML plano; cualquier otra estructura es un error a propósito."""
    config: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = raw.partition(":")
        if not separator or key != key.strip() or key not in CONFIG_KEYS:
            raise ExerciseError(f"{path.name}:{number}: clave no permitida ({line})")
        config[key] = value.strip().strip("\"'")
    missing = CONFIG_KEYS - config.keys()
    if missing:
        raise ExerciseError(f"{path.name}: faltan claves: {', '.join(sorted(missing))}")
    return config


def validate_config(config: dict[str, str], template: bool) -> None:
    if not config["port"].isdigit() or not 1024 <= int(config["port"]) <= 65535:
        raise ExerciseError("exercise.yaml: port debe estar entre 1024 y 65535")
    if not template and not OWNER_RE.match(config["owner"]):
        raise ExerciseError("exercise.yaml: owner debe ser tu usuario de GitHub")
    if not 0 < len(config["description"]) <= 200:
        raise ExerciseError("exercise.yaml: description debe tener entre 1 y 200 caracteres")


def validate_dockerfile(path: Path) -> None:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    froms = [i for i, line in enumerate(lines) if line.upper().startswith("FROM ")]
    if not froms:
        raise ExerciseError("Dockerfile: no tiene FROM")
    for index in froms:
        image = lines[index].split()[1]
        if image.endswith(":latest") or (":" not in image and "@" not in image):
            raise ExerciseError(f"Dockerfile: fija la versión de la imagen base ({image})")
    users = [line for line in lines[froms[-1]:] if line.upper().startswith("USER ")]
    match = re.match(r"(?i)^USER\s+(\d+)(:\d+)?$", users[-1]) if users else None
    if match is None or int(match.group(1)) == 0:
        raise ExerciseError("Dockerfile: la etapa final necesita USER numérico distinto de 0")


def validate_exercise(name: str, base: Path = EXERCISES) -> None:
    folder = base / name
    template = is_template(name)
    if not template and not NAME_RE.match(name):
        raise ExerciseError(f"{name}: usa minúsculas, números y guiones (2 a 31 caracteres)")
    for required in REQUIRED_FILES:
        if not (folder / required).is_file():
            raise ExerciseError(f"{name}: falta {required}")
    total = 0
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ExerciseError(f"{name}: no se admiten enlaces simbólicos ({path.name})")
        if path.is_file():
            if FORBIDDEN_NAMES.match(path.name):
                raise ExerciseError(f"{name}: archivo no permitido ({path.name})")
            total += path.stat().st_size
    if total > MAX_BYTES:
        raise ExerciseError(f"{name}: la carpeta supera {MAX_BYTES} bytes")
    validate_config(parse_config(folder / "exercise.yaml"), template)
    validate_dockerfile(folder / "Dockerfile")


def validate_all(base: Path = EXERCISES) -> None:
    names = public_exercises(base)
    if len(names) > MAX_EXERCISES:
        raise ExerciseError(f"hay {len(names)} ejercicios y el máximo es {MAX_EXERCISES}")
    for name in list_dirs(base):
        validate_exercise(name, base)


def changed_files(base: str, head: str) -> list[str]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in output.splitlines() if line]


def touched_names(files: list[str]) -> set[str]:
    return {f.split("/")[1] for f in files if f.startswith("exercises/") and f.count("/") >= 2}


def enforce_scope(files: list[str]) -> None:
    """Un PR de estudiante solo puede tocar una carpeta suya dentro de exercises/."""
    outside = [f for f in files if not f.startswith("exercises/") or f.count("/") < 2]
    if outside:
        raise ExerciseError(f"el PR modifica archivos fuera de tu carpeta: {', '.join(outside)}")
    names = touched_names(files)
    if len(names) != 1:
        raise ExerciseError(f"el PR debe tocar exactamente una carpeta: {sorted(names)}")
    if is_template(next(iter(names))):
        raise ExerciseError("no modifiques la carpeta de ejemplo: cópiala con tu nombre")


def plan(base: str, head: str, scope: bool, root: Path = EXERCISES) -> tuple[list[str], list[str]]:
    if base == ZERO_SHA:
        return public_exercises(root), []
    files = changed_files(base, head)
    if scope:
        enforce_scope(files)
    names = {name for name in touched_names(files) if not is_template(name)}
    changed = sorted(name for name in names if (root / name).is_dir())
    return changed, sorted(names - set(changed))


def render_values(name: str, sha: str, port: int) -> str:
    if not SHA_RE.match(sha):
        raise ExerciseError("sha debe tener 40 caracteres hexadecimales")
    return f"""# Generado por .github/workflows/exercises.yml. No lo edites a mano.
image:
  repository: {REGISTRY}
  tag: {name}-{sha}
replicaCount: 1
containerPort: {port}
terminationGracePeriodSeconds: 15
resources:
  requests: {{ cpu: 50m, memory: 64Mi }}
  limits: {{ cpu: 100m, memory: 128Mi }}
dapr:
  enabled: false
keda:
  enabled: false
pdb:
  enabled: false
externalSecret:
  enabled: false
networkPolicy:
  enabled: true
  ingress:
    traefik: true
  egress:
    daprControlPlane: false
    otlp: false
ingress:
  enabled: true
  path: /s/{name}
  middlewares: {MIDDLEWARES}
"""


def write_values(name: str, sha: str, out_dir: Path) -> None:
    config = parse_config(EXERCISES / name / "exercise.yaml")
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "values.yaml").write_text(
        render_values(name, sha, int(config["port"])), encoding="utf-8", newline="\n"
    )


def emit(key: str, value: object) -> None:
    line = f"{key}={json.dumps(value)}"
    print(line)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(line + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    plan_cmd = commands.add_parser("plan")
    plan_cmd.add_argument("--base", required=True)
    plan_cmd.add_argument("--head", required=True)
    plan_cmd.add_argument("--scope", action="store_true")
    render_cmd = commands.add_parser("render")
    render_cmd.add_argument("name")
    render_cmd.add_argument("--sha", required=True)
    render_cmd.add_argument("--out-dir", required=True, type=Path)
    sync_cmd = commands.add_parser("sync")
    sync_cmd.add_argument("--changed", required=True)
    sync_cmd.add_argument("--removed", required=True)
    sync_cmd.add_argument("--sha", required=True)
    sync_cmd.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if args.command == "check":
            validate_all()
            print("ejercicios válidos")
        elif args.command == "plan":
            validate_all()
            changed, removed = plan(args.base, args.head, args.scope)
            emit("changed", changed)
            emit("removed", removed)
        elif args.command == "render":
            write_values(args.name, args.sha, args.out_dir)
        else:
            for name in json.loads(args.changed):
                write_values(name, args.sha, args.out_dir)
            for name in json.loads(args.removed):
                shutil.rmtree(args.out_dir / name, ignore_errors=True)
    except ExerciseError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
