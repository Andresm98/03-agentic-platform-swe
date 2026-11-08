#!/usr/bin/env bash
# Prueba de humo de `make compose-up`: una tarea recorre toda la flota con 0 tokens live.
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8001}"
BASE="${BASE%/}"
# Con researcher y analyst en 0 réplicas, la primera tarea espera a KEDA y al arranque de sus pods.
TASK_TIMEOUT_S="${TASK_TIMEOUT_S:-60}"
GW="${GW:-http://127.0.0.1:8002}"
PY="$(command -v python || command -v python3)"
field() { "$PY" -c "import json,sys;d=json.load(sys.stdin);print(d.get('$1',''))"; }

# Por el NLB solo se expone /tasks: post-deploy.yml usa SKIP_READYZ=1.
if [[ -z "${SKIP_READYZ:-}" ]]; then
  for _ in $(seq 1 60); do
    [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/readyz")" == 200 ]] && break
    sleep 2
  done
  curl -sf "$BASE/readyz"; echo
fi
resp="$(curl -sf -X POST "$BASE/tasks" -H 'content-type: application/json' \
  -d '{"goal":"Explica el autoscaling de la flota y su coste","complexity":2}')"
echo "$resp"
tid="$(echo "$resp" | field task_id)"
for _ in $(seq 1 "$TASK_TIMEOUT_S"); do
  body="$(curl -s "$BASE/tasks/$tid")"
  status="$(echo "$body" | field status)"
  [[ "$status" == completed || "$status" == failed ]] && break
  sleep 1
done
echo "$body"
[[ "$status" == completed ]] || { echo "ERROR: la tarea terminó en '$status'" >&2; exit 1; }
bad="$(echo "$body" | "$PY" -c "import json,sys;print(sum(1 for s in json.load(sys.stdin)['steps'] if s['status']!='ok'))")"
[[ "$bad" == 0 ]] || { echo "ERROR: $bad pasos sin status=ok" >&2; exit 1; }
live="$(curl -s --max-time 5 "$GW/metrics" | grep '^llm_tokens_total' | grep 'mode="live"' || true)"
[[ -z "$live" ]] || { echo "ERROR: hay tokens live: $live" >&2; exit 1; }
echo "OK: tarea $tid completada con 0 tokens live"
