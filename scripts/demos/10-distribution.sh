#!/usr/bin/env bash
# Escenario 10: las peticiones se reparten entre réplicas (cabecera X-Pod-Name).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
step "Muestra de 100 peticiones"
BASE="$(base_url)"
pods="$(for i in $(seq 1 100); do curl -s -o /dev/null -D - -X POST "$BASE/tasks" -H 'content-type: application/json' -d '{"goal":"Reparto","complexity":1}' | tr -d '\r' | awk 'tolower($1)=="x-pod-name:"{print $2}'; done)"
echo "$pods" | sort | uniq -c
assert_ge "$(echo "$pods" | grep -c .)" 1 "respuestas con X-Pod-Name"
assert_ge "$(echo "$pods" | sort -u | grep -c .)" "${MIN_PODS:-1}" "pods distintos"
demo_summary
