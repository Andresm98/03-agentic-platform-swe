#!/usr/bin/env bash
# infra/scripts/lib.sh: funciones comunes de los scripts de infraestructura (equipo P).
# Uso: source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck disable=SC2034  # Las constantes las usan los scripts que cargan esta librería.

if [[ -n "${__INFRA_LIB_LOADED:-}" ]]; then
  return 0
fi
__INFRA_LIB_LOADED=1

# En Git Bash, MSYS reescribe los argumentos y variables que empiezan por "/": la ruta SSM
# /agentic-platform/... llegaba a la AWS CLI como C:/Program Files/Git/agentic-platform/...
export MSYS_NO_PATHCONV=1

# Con la conversión desactivada, las rutas locales deben ir ya en formato nativo: `pwd -W` da
# C:/Users/... en Git Bash y falla en Linux, donde vale `pwd`.
INFRA_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && { pwd -W 2>/dev/null || pwd; })"
readonly INFRA_REPO_ROOT
readonly INFRA_TF_DIR="$INFRA_REPO_ROOT/infra/terraform"
readonly INFRA_LAB_DIR="$INFRA_TF_DIR/envs/lab"
readonly INFRA_BOOTSTRAP_DIR="$INFRA_TF_DIR/bootstrap"
readonly INFRA_STATE_DIR="$INFRA_REPO_ROOT/.lab" # ignorado por Git
readonly PROJECT_TAG="agentic-platform"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
warn() { printf '[%s] WARN: %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() {
  printf '[%s] ERROR: %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2
  exit 1
}

# native_path <ruta>: ruta entendible por los ejecutables nativos de Windows (aws, python);
# fuera de Git Bash la devuelve igual.
native_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s' "$1"
  fi
}

# require_cmd <cmd>...: falla con un mensaje claro si falta alguna herramienta.
require_cmd() {
  local missing=() c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  ((${#missing[@]} == 0)) || die "faltan herramientas: ${missing[*]} (ver docs/runbook.md)"
}

# require_env <VAR>...: falla si alguna variable está vacía o sin definir.
require_env() {
  local missing=() v
  for v in "$@"; do
    [[ -n "${!v:-}" ]] || missing+=("$v")
  done
  ((${#missing[@]} == 0)) || die "faltan variables de entorno: ${missing[*]}"
}

# find_python: exporta PYTHON con un intérprete que funcione de verdad (en Windows,
# "python3" puede ser el alias de la Microsoft Store, que existe pero no ejecuta nada).
find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json, secrets' >/dev/null 2>&1; then
      PYTHON="$candidate"
      export PYTHON
      return 0
    fi
  done
  die "no hay un Python 3 operativo (python3/python)"
}

# confirm <pregunta>: pide confirmación salvo con AUTO_APPROVE=1 (CI).
confirm() {
  [[ "${AUTO_APPROVE:-0}" == "1" ]] && return 0
  local answer
  read -r -p "$1 [escribe 'si' para continuar]: " answer
  [[ "$answer" == "si" ]] || die "cancelado por el usuario"
}

# aws_identity: comprueba credenciales y devuelve el account ID.
aws_account_id() {
  aws sts get-caller-identity --query Account --output text 2>/dev/null \
    || die "sin credenciales AWS válidas (aws sts get-caller-identity falló)"
}

# tf_backend_args: argumentos -backend-config para envs/lab.
#   TF_STATE_BUCKET=<bucket> o infra/terraform/envs/lab/backend.hcl
tf_backend_args() {
  if [[ -n "${TF_STATE_BUCKET:-}" ]]; then
    printf '%s\n' "-backend-config=bucket=$TF_STATE_BUCKET"
  elif [[ -f "$INFRA_LAB_DIR/backend.hcl" ]]; then
    printf '%s\n' "-backend-config=backend.hcl"
  else
    die "define TF_STATE_BUCKET o crea envs/lab/backend.hcl (ver backend.hcl.example)"
  fi
}

# tf_lab <args...>: terraform sobre envs/lab.
tf_lab() {
  terraform -chdir="$INFRA_LAB_DIR" "$@"
}

# tf_lab_init: init idempotente del backend remoto.
tf_lab_init() {
  local backend_arg
  backend_arg="$(tf_backend_args)"
  tf_lab init -input=false -reconfigure "$backend_arg" >/dev/null || die "terraform init falló en envs/lab"
}

# lab_output <nombre>: output de envs/lab (requiere init previo).
lab_output() {
  tf_lab output -raw "$1" 2>/dev/null || die "no existe el output '$1' (¿lab levantado?)"
}
