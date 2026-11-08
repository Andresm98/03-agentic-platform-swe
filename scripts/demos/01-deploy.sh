#!/usr/bin/env bash
# Escenario 1: despliegue normal. Applications Healthy y POST /tasks responde 202.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
step "Applications de la flota"
for app in fleet-dapr-components fleet-fake-llm fleet-llm-gateway fleet-orchestrator fleet-researcher fleet-analyst fleet-executor; do
  wait_until 300 bash -c "[[ \"\$(kubectl -n argocd get application $app -o jsonpath='{.status.health.status}/{.status.sync.status}')\" == Healthy/Synced ]]"
done
step "Petición de humo"
BASE="$(base_url)"
code="$(curl -s -o /tmp/demo01.json -w '%{http_code}' -X POST "$BASE/tasks" -H 'content-type: application/json' -d '{"goal":"Comprueba el despliegue","complexity":1}')"
assert_eq "$code" 202 "POST /tasks"
assert_contains "$(cat /tmp/demo01.json)" task_id "respuesta"
demo_summary
