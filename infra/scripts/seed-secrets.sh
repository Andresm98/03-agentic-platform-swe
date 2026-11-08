#!/usr/bin/env bash
# seed-secrets.sh: crea/actualiza los SecureString de CONTRACTS §6 a partir de variables de
# entorno. Nunca contiene valores por defecto reales. Los valores no pasan por la línea de
# comandos (se envían con --cli-input-json desde un fichero temporal 0600).
#
# Variables OBLIGATORIAS (secretos externos):
#   OPENAI_API_KEY                      -> /agentic-platform/k8s/openai-api-key
#   LANGSMITH_API_KEY                   -> /agentic-platform/k8s/langsmith-api-key
#   GRAFANA_PROM_URL, GRAFANA_PROM_USER,
#   GRAFANA_LOKI_URL, GRAFANA_LOKI_USER,
#   GRAFANA_OTLP_URL, GRAFANA_OTLP_USER,
#   GRAFANA_CLOUD_TOKEN                 -> /agentic-platform/k8s/grafana-cloud (JSON)
#   GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID,
#   GITHUB_APP_PRIVATE_KEY_FILE (ruta al .pem) -> /agentic-platform/k8s/github-app (JSON)
#
# Variables de secretos INTERNOS (obligatorias salvo GENERATE_INTERNAL=1, que genera
# valores aleatorios de 32 bytes):
#   DEMO_TOKEN                          -> /agentic-platform/k8s/demo-token
#   REDIS_PASSWORD                      -> /agentic-platform/k8s/redis-password
#   NATS_PASSWORD_<SERVICIO>            -> /agentic-platform/k8s/nats/<servicio>-password
#     (SERVICIO en mayúsculas con '_': ORCHESTRATOR, RESEARCHER, ANALYST, EXECUTOR,
#      LLM_GATEWAY, FAKE_LLM)
#
# Otras: DRY_RUN=1 (solo lista qué escribiría, sin llamar a AWS), OVERWRITE=0 (no pisa
# parámetros existentes; por defecto 1).
# Uso: make seed-secrets
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly PREFIX="/agentic-platform/k8s"
readonly FLEET_SERVICES=(orchestrator researcher analyst executor llm-gateway fake-llm)
TMP_DIR=""

cleanup() { [[ -n "$TMP_DIR" ]] && rm -rf "$TMP_DIR"; }
trap cleanup EXIT

random_secret() {
  # Hex con prefijo: NATS interpreta el valor de la variable y rechaza contraseñas tipo 12-abc.
  "$PYTHON" -c 'import secrets; print("s" + secrets.token_hex(32))'
}

# env_name_for <servicio>: orchestrator -> NATS_PASSWORD_ORCHESTRATOR
env_name_for() {
  local svc="${1^^}"
  printf 'NATS_PASSWORD_%s' "${svc//-/_}"
}

# internal_secret <VAR>: valor de la variable o, con GENERATE_INTERNAL=1, uno aleatorio.
internal_secret() {
  local var="$1"
  if [[ -n "${!var:-}" ]]; then
    printf '%s' "${!var}"
  elif [[ "${GENERATE_INTERNAL:-0}" == "1" ]]; then
    random_secret
  else
    die "falta $var (o usa GENERATE_INTERNAL=1 para generarlo)"
  fi
}

check_inputs() {
  require_env OPENAI_API_KEY LANGSMITH_API_KEY \
    GRAFANA_PROM_URL GRAFANA_PROM_USER GRAFANA_LOKI_URL GRAFANA_LOKI_USER \
    GRAFANA_OTLP_URL GRAFANA_OTLP_USER GRAFANA_CLOUD_TOKEN \
    GITHUB_APP_ID GITHUB_APP_INSTALLATION_ID GITHUB_APP_PRIVATE_KEY_FILE
  [[ -r "$GITHUB_APP_PRIVATE_KEY_FILE" ]] || die "no se puede leer GITHUB_APP_PRIVATE_KEY_FILE=$GITHUB_APP_PRIVATE_KEY_FILE"
  grep -q 'PRIVATE KEY' "$GITHUB_APP_PRIVATE_KEY_FILE" || die "GITHUB_APP_PRIVATE_KEY_FILE no parece una clave PEM"
  GITHUB_APP_PRIVATE_KEY_FILE="$(native_path "$GITHUB_APP_PRIVATE_KEY_FILE")"
  export GITHUB_APP_PRIVATE_KEY_FILE
}

# grafana_json / github_app_json: JSON construido con python (escapado correcto).
grafana_json() {
  "$PYTHON" - <<'PY'
import json, os
print(json.dumps({
    "prom_url": os.environ["GRAFANA_PROM_URL"], "prom_user": os.environ["GRAFANA_PROM_USER"],
    "loki_url": os.environ["GRAFANA_LOKI_URL"], "loki_user": os.environ["GRAFANA_LOKI_USER"],
    "otlp_url": os.environ["GRAFANA_OTLP_URL"], "otlp_user": os.environ["GRAFANA_OTLP_USER"],
    "token": os.environ["GRAFANA_CLOUD_TOKEN"],
}))
PY
}

github_app_json() {
  "$PYTHON" - <<'PY'
import json, os
with open(os.environ["GITHUB_APP_PRIVATE_KEY_FILE"], encoding="utf-8") as f:
    key = f.read()
print(json.dumps({
    "appID": os.environ["GITHUB_APP_ID"],
    "installationID": os.environ["GITHUB_APP_INSTALLATION_ID"],
    "privateKey": key,
}))
PY
}

# put_secure <nombre> <valor>: SecureString vía fichero temporal (el valor no aparece en ps).
put_secure() {
  local name="$1" value="$2" input
  [[ -n "$value" ]] || die "valor vacío para $name (fallo al construirlo)"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "[dry-run] escribiría $name (${#value} caracteres)"
    return 0
  fi
  input="$TMP_DIR/param.json"
  NAME="$name" VALUE="$value" OVERWRITE="${OVERWRITE:-1}" "$PYTHON" - >"$input" <<'PY'
import json, os
print(json.dumps({"Name": os.environ["NAME"], "Value": os.environ["VALUE"], "Type": "SecureString",
                  "Overwrite": os.environ["OVERWRITE"] == "1", "Tier": "Standard"}))
PY
  if aws ssm put-parameter --cli-input-json "file://$(native_path "$input")" >/dev/null; then
    log "escrito $name"
  elif [[ "${OVERWRITE:-1}" == "0" ]]; then
    warn "$name ya existe; se conserva (OVERWRITE=0)"
  else
    die "no se pudo escribir $name"
  fi
  rm -f "$input"
}

tag_parameters() {
  [[ "${DRY_RUN:-0}" == "1" ]] && return 0
  local name
  for name in "$@"; do
    aws ssm add-tags-to-resource --resource-type Parameter --resource-id "$name" \
      --tags "Key=Project,Value=$PROJECT_TAG" "Key=Lifecycle,Value=persistent" >/dev/null \
      || warn "no se pudo etiquetar $name"
  done
}

main() {
  find_python
  [[ "${DRY_RUN:-0}" == "1" ]] || require_cmd aws
  check_inputs
  TMP_DIR="$(mktemp -d)"
  chmod 700 "$TMP_DIR"
  [[ "${DRY_RUN:-0}" == "1" ]] || log "cuenta AWS $(aws_account_id), región $AWS_REGION"

  local written=() svc value
  # Cada valor se asigna antes de usarlo: así un fallo al construirlo aborta (set -e).
  local -A params=()
  params["$PREFIX/openai-api-key"]="$OPENAI_API_KEY"
  params["$PREFIX/langsmith-api-key"]="$LANGSMITH_API_KEY"
  value="$(grafana_json)"
  params["$PREFIX/grafana-cloud"]="$value"
  value="$(github_app_json)"
  params["$PREFIX/github-app"]="$value"
  value="$(internal_secret DEMO_TOKEN)"
  params["$PREFIX/demo-token"]="$value"
  value="$(internal_secret REDIS_PASSWORD)"
  params["$PREFIX/redis-password"]="$value"
  for svc in "${FLEET_SERVICES[@]}"; do
    value="$(internal_secret "$(env_name_for "$svc")")"
    params["$PREFIX/nats/$svc-password"]="$value"
  done

  local name
  for name in "${!params[@]}"; do
    put_secure "$name" "${params[$name]}"
    written+=("$name")
  done

  tag_parameters "${written[@]}"
  log "listo: ${#written[@]} parámetros bajo $PREFIX"
}

main "$@"
