#!/usr/bin/env bash
# validate.sh: validación estática de la capa del equipo P (sin AWS ni cluster).
#   - terraform fmt -check y validate (init -backend=false) en cada raíz y módulo
#   - tflint, checkov, shellcheck y kubeconform si están instalados (STRICT=1 los exige)
#   - bash -n de todos los scripts
#   - YAML parseable, kustomize build de los overlays
#   - helm template de cada platform-*.yaml con sus values (VALIDATE_HELM=1; usa red)
# Uso: validate.sh [paso...]  (sin argumentos, todos). Pasos: terraform tflint checkov
#      shell shellcheck yaml kustomize kubeconform helm. CI ejecuta cada uno por separado.
# Sale con 1 si algún paso falla.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

FAILED=()
STEPS=("$@")
cd "$INFRA_REPO_ROOT"

# want <paso>: 0 si el paso está seleccionado (sin argumentos se ejecutan todos).
want() {
  ((${#STEPS[@]} == 0)) && return 0
  local step
  for step in "${STEPS[@]}"; do
    [[ "$step" == "$1" ]] && return 0
  done
  return 1
}

# run_step <nombre> <cmd...>: ejecuta y registra el resultado sin abortar el resto.
run_step() {
  local name="$1"
  shift
  log "== $name"
  if "$@"; then
    log "OK  $name"
  else
    warn "FAIL $name"
    FAILED+=("$name")
  fi
}

# optional_tool <cmd>: 0 si existe; si falta, lo avisa (o falla con STRICT=1).
optional_tool() {
  command -v "$1" >/dev/null 2>&1 && return 0
  if [[ "${STRICT:-0}" == "1" ]]; then
    warn "falta $1 (STRICT=1)"
    FAILED+=("tool:$1")
  else
    warn "omitido: $1 no está instalado"
  fi
  return 1
}

terraform_roots() {
  find infra/terraform observability/terraform -name '*.tf' -not -path '*/.terraform/*' -print0 2>/dev/null \
    | xargs -0 -n1 dirname | sort -u
}

shell_scripts() {
  find infra/scripts scripts/local -name '*.sh' 2>/dev/null
  find scripts/demos -name '0[789]-*.sh' -o -name '1[12]-*.sh' 2>/dev/null
}

tf_fmt() { terraform fmt -check -recursive -diff infra/terraform observability/terraform; }

tf_validate() {
  local dir rc=0
  while read -r dir; do
    terraform -chdir="$dir" init -backend=false -input=false >/dev/null && terraform -chdir="$dir" validate -no-color >/dev/null \
      || {
        warn "terraform validate falló en $dir"
        rc=1
      }
    # El lock solo se versiona en las raíces, no en los módulos.
    if [[ "$dir" == */modules/* ]]; then rm -f "$dir/.terraform.lock.hcl"; fi
  done < <(terraform_roots)
  return "$rc"
}

tf_lint() { tflint --chdir=infra/terraform --recursive --format=compact; }

tf_checkov() {
  checkov --quiet --compact --framework terraform -d infra/terraform -d observability/terraform
}

sh_syntax() {
  local f rc=0
  while read -r f; do bash -n "$f" || rc=1; done < <(shell_scripts)
  return "$rc"
}

sh_check() {
  local files=()
  mapfile -t files < <(shell_scripts)
  shellcheck -x -S warning "${files[@]}"
}

yaml_parse() {
  "$PYTHON" - <<'PY'
import pathlib, sys, yaml
bad = 0
for root in ("gitops", "kubernetes/bootstrap", "observability", ".github/workflows"):
    for p in pathlib.Path(root).rglob("*.y*ml"):
        try:
            list(yaml.safe_load_all(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"YAML inválido: {p}: {e}", file=sys.stderr)
            bad = 1
sys.exit(bad)
PY
}

kustomize_builds() {
  local d rc=0
  for d in gitops/clusters/local-k3d gitops/platform/redis gitops/platform/argocd-notifications; do
    kubectl kustomize --load-restrictor LoadRestrictionsNone "$d" >/dev/null || {
      warn "kustomize build falló en $d"
      rc=1
    }
  done
  return "$rc"
}

kube_conform() {
  find gitops/platform gitops/clusters gitops/argocd-apps kubernetes/bootstrap -name '*.yaml' -not -name 'values.yaml' \
    -not -path '*/values/*' -not -name 'kustomization.yaml' -print0 \
    | xargs -0 kubeconform -strict -summary -ignore-missing-schemas \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
}

# helm_render: helm template de cada Application de plataforma con chart (values comunes
# + overlay aws-lab), como lo hará Argo CD.
helm_render() {
  "$PYTHON" - <<'PY'
import pathlib, subprocess, sys, yaml
rc = 0
for app in sorted(pathlib.Path("gitops/argocd-apps").glob("platform-*.yaml")):
    spec = yaml.safe_load(app.read_text(encoding="utf-8"))["spec"]
    for src in spec.get("sources", []):
        if "chart" not in src:
            continue
        files = []
        for vf in src["helm"].get("valueFiles", []):
            p = pathlib.Path(vf.replace("$values/", ""))
            if p.exists():
                files += ["-f", str(p)]
        cmd = ["helm", "template", src["helm"]["releaseName"], src["chart"], "--repo", src["repoURL"],
               "--version", src["targetRevision"], "-n", spec["destination"]["namespace"], *files]
        r = subprocess.run(cmd, capture_output=True, text=True)
        status = "OK  " if r.returncode == 0 else "FAIL"
        print(f"{status} {app.name}: {src['chart']} {src['targetRevision']}", file=sys.stderr)
        if r.returncode:
            print(r.stderr[-2000:], file=sys.stderr)
            rc = 1
sys.exit(rc)
PY
}

main() {
  find_python
  if want terraform; then
    require_cmd terraform
    run_step "terraform fmt" tf_fmt
    run_step "terraform validate" tf_validate
  fi
  if want tflint && optional_tool tflint; then run_step "tflint" tf_lint; fi
  if want checkov && optional_tool checkov; then run_step "checkov" tf_checkov; fi
  if want shell; then run_step "bash -n" sh_syntax; fi
  if want shellcheck && optional_tool shellcheck; then run_step "shellcheck" sh_check; fi
  if want yaml; then run_step "yaml" yaml_parse; fi
  if want kustomize && optional_tool kubectl; then run_step "kustomize build" kustomize_builds; fi
  if want kubeconform && optional_tool kubeconform; then run_step "kubeconform" kube_conform; fi
  # helm usa red: se ejecuta si se pide por nombre o con VALIDATE_HELM=1.
  if [[ " ${STEPS[*]-} " == *" helm "* || "${VALIDATE_HELM:-0}" == "1" ]] && optional_tool helm; then
    run_step "helm template (platform)" helm_render
  fi

  if ((${#FAILED[@]})); then
    die "validación con fallos: ${FAILED[*]}"
  fi
  log "validación de la capa P: OK"
}

main "$@"
