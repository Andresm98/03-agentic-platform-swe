#!/usr/bin/env bash
# Escenario 14: fake-llm con 30 % de 5xx. El circuito se abre y ningún task_id se pierde.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_cmd docker
pf="$(pf_service fake-llm 18003)"
trap 'k6_stop; kill "$pf" 2>/dev/null || true' EXIT
sleep 2
step "Inyección de fallos"
curl -sf -X PUT http://127.0.0.1:18003/admin/faults -H 'content-type: application/json' -d '{"error_rate_500":0.3,"latency_median_ms":800}'; echo
step "Carga con k6 y borrado de pods"
BASE="$(base_url)"
k6_run chaos.js "BASE_URL=$BASE" "DURATION=${DURATION:-2m}" >/tmp/demo14.log 2>&1 &
K6=$!
sleep 30
kubectl -n apps delete pod -l app.kubernetes.io/name=orchestrator --wait=false
wait "$K6" || true
curl -sf -X PUT http://127.0.0.1:18003/admin/faults -H 'content-type: application/json' -d '{"error_rate_500":0,"latency_median_ms":300}'; echo
step "Reconciliación de task_id"
ids="$(grep -oE 'TASK [0-9a-f-]{36}' /tmp/demo14.log | awk '{print $2}' | sort -u)"
total="$(echo "$ids" | grep -c . || true)"
assert_ge "$total" 1 "tareas aceptadas"
sleep "${SETTLE:-180}"
lost=0
for id in $ids; do
  status="$(curl -s "$BASE/tasks/$id" | python -c 'import json,sys;print(json.load(sys.stdin).get("status",""))')"
  [[ "$status" == completed || "$status" == failed ]] || { lost=$((lost + 1)); warn "$id: '$status'"; }
done
assert_eq "$lost" 0 "task_id sin estado final"
demo_summary
