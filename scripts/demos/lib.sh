#!/usr/bin/env bash
# scripts/demos/lib.sh: funciones comunes para los scripts de demo NN-nombre.sh.
#
# Uso (dentro de cada script):
#   #!/usr/bin/env bash
#   set -euo pipefail
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Variables de entorno:
#   NO_COLOR=1         desactiva el color (también se desactiva si stdout no es un TTY)
#   DEMO_POLL_SECONDS  intervalo de sondeo de wait_until (por defecto 5)
#   DEMO_VERBOSE=1     muestra la salida de los comandos sondeados por wait_until
#
# Convención: cualquier assert que falla termina el script con código 1.
# Los errores de uso (argumentos mal pasados a una función) terminan con código 2.

# Evita cargar la librería dos veces.
if [[ -n "${__DEMO_LIB_LOADED:-}" ]]; then
  return 0
fi
__DEMO_LIB_LOADED=1

DEMO_POLL_SECONDS="${DEMO_POLL_SECONDS:-5}"
DEMO_NAME="${DEMO_NAME:-$(basename "${0%.sh}")}"
DEMO_STEP=0
DEMO_ASSERTS_OK=0

# --- Color -------------------------------------------------------------------------

if [[ -z "${NO_COLOR:-}" && -t 1 && "${TERM:-}" != "dumb" ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

# --- Tiempo ------------------------------------------------------------------------

# ts: timestamp ISO-8601 en UTC, para pegar en docs/validation-log.md.
ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# now_epoch: segundos desde epoch (para medir duraciones).
now_epoch() {
  date +%s
}

DEMO_START_EPOCH="$(now_epoch)"
DEMO_START_TS="$(ts)"

# elapsed: segundos transcurridos desde que se cargó la librería.
elapsed() {
  echo $(( $(now_epoch) - DEMO_START_EPOCH ))
}

# --- Log ---------------------------------------------------------------------------

log() {
  printf '%s[%s]%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$*"
}

info() {
  printf '%s[%s]%s %s%s%s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_BLUE" "$*" "$C_RESET"
}

warn() {
  printf '%s[%s]%s %sWARN:%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_YELLOW" "$C_RESET" "$*" >&2
}

die() {
  printf '%s[%s]%s %sERROR:%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2
  exit 1
}

# step "<descripción>": encabezado numerado de un paso de la demo.
step() {
  DEMO_STEP=$((DEMO_STEP + 1))
  printf '\n%s[%s] == Paso %d: %s%s\n' "$C_BOLD" "$(ts)" "$DEMO_STEP" "$*" "$C_RESET"
}

_pass() {
  DEMO_ASSERTS_OK=$((DEMO_ASSERTS_OK + 1))
  printf '%s[%s]%s %sPASS%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_GREEN" "$C_RESET" "$*"
}

_fail() {
  printf '%s[%s]%s %sFAIL%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2
  exit 1
}

# --- Requisitos --------------------------------------------------------------------

# require_cmd <cmd>...: falla si falta alguno de los comandos.
require_cmd() {
  local missing=() c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  if ((${#missing[@]} > 0)); then
    die "faltan comandos requeridos: ${missing[*]}"
  fi
}

# require_env <VAR>...: falla si alguna variable de entorno está vacía o sin definir.
require_env() {
  local missing=() v
  for v in "$@"; do
    [[ -n "${!v:-}" ]] || missing+=("$v")
  done
  if ((${#missing[@]} > 0)); then
    die "faltan variables de entorno: ${missing[*]}"
  fi
}

# --- Asserts -----------------------------------------------------------------------

# assert_eq <actual> <esperado> [mensaje]
assert_eq() {
  if (($# < 2)); then
    echo "assert_eq: uso: assert_eq <actual> <esperado> [mensaje]" >&2
    exit 2
  fi
  local actual="$1" expected="$2" msg="${3:-valor}"
  if [[ "$actual" == "$expected" ]]; then
    _pass "$msg: '$actual' == '$expected'"
  else
    _fail "$msg: se esperaba '$expected' y se obtuvo '$actual'"
  fi
}

# assert_ge <actual> <mínimo> [mensaje]: comparación numérica entera (actual >= mínimo).
assert_ge() {
  if (($# < 2)); then
    echo "assert_ge: uso: assert_ge <actual> <mínimo> [mensaje]" >&2
    exit 2
  fi
  local actual="$1" min="$2" msg="${3:-valor}"
  if ! [[ "$actual" =~ ^-?[0-9]+$ && "$min" =~ ^-?[0-9]+$ ]]; then
    _fail "$msg: comparación no numérica ('$actual' >= '$min')"
  fi
  if ((actual >= min)); then
    _pass "$msg: $actual >= $min"
  else
    _fail "$msg: se esperaba >= $min y se obtuvo $actual"
  fi
}

# assert_le <actual> <máximo> [mensaje]: comparación numérica entera (actual <= máximo).
assert_le() {
  if (($# < 2)); then
    echo "assert_le: uso: assert_le <actual> <máximo> [mensaje]" >&2
    exit 2
  fi
  local actual="$1" max="$2" msg="${3:-valor}"
  if ! [[ "$actual" =~ ^-?[0-9]+$ && "$max" =~ ^-?[0-9]+$ ]]; then
    _fail "$msg: comparación no numérica ('$actual' <= '$max')"
  fi
  if ((actual <= max)); then
    _pass "$msg: $actual <= $max"
  else
    _fail "$msg: se esperaba <= $max y se obtuvo $actual"
  fi
}

# assert_contains <texto> <subcadena> [mensaje]
assert_contains() {
  if (($# < 2)); then
    echo "assert_contains: uso: assert_contains <texto> <subcadena> [mensaje]" >&2
    exit 2
  fi
  local haystack="$1" needle="$2" msg="${3:-texto}"
  if [[ "$haystack" == *"$needle"* ]]; then
    _pass "$msg contiene '$needle'"
  else
    _fail "$msg no contiene '$needle'"
  fi
}

# --- Espera ------------------------------------------------------------------------

# wait_until <timeout_segundos> <cmd> [args...]
# Ejecuta el comando cada DEMO_POLL_SECONDS hasta que sale con 0 o se agota el tiempo.
# Devuelve 0 si se cumplió y termina el script con 1 si se agotó el tiempo.
# Para expresiones con tuberías: wait_until 300 bash -c 'kubectl get nodes | grep -c Ready | grep -q 3'
wait_until() {
  if (($# < 2)); then
    echo "wait_until: uso: wait_until <timeout_segundos> <cmd> [args...]" >&2
    exit 2
  fi
  local timeout="$1"; shift
  if ! [[ "$timeout" =~ ^[0-9]+$ ]]; then
    echo "wait_until: el timeout debe ser un entero en segundos (recibido '$timeout')" >&2
    exit 2
  fi
  local start deadline attempt=0
  start="$(now_epoch)"
  deadline=$((start + timeout))
  log "esperando (máx. ${timeout}s): $*"
  while true; do
    attempt=$((attempt + 1))
    if [[ -n "${DEMO_VERBOSE:-}" ]]; then
      if "$@"; then break; fi
    else
      if "$@" >/dev/null 2>&1; then break; fi
    fi
    if (($(now_epoch) >= deadline)); then
      _fail "timeout tras ${timeout}s (${attempt} intentos): $*"
    fi
    sleep "$DEMO_POLL_SECONDS"
  done
  _pass "condición cumplida en $(($(now_epoch) - start))s (${attempt} intentos): $*"
}

# --- Resumen -----------------------------------------------------------------------

# demo_summary: imprime el resumen final (llamarlo al terminar el script).
demo_summary() {
  printf '\n%s[%s] %s: OK, %d asserts superados en %ss (inicio %s)%s\n' \
    "$C_GREEN" "$(ts)" "$DEMO_NAME" "$DEMO_ASSERTS_OK" "$(elapsed)" "$DEMO_START_TS" "$C_RESET"
}
