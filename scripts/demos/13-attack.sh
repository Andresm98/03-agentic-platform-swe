#!/usr/bin/env bash
# Escenario 13: ataque (token falso, ráfagas, payloads grandes). Debe gastar 0 tokens live.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_cmd docker
step "Línea base"
live_before="$(metric_sum llm-gateway '^llm_tokens_total.*mode="live"')"
shed_before="$(metric_sum orchestrator '^tasks_shed_total')"
step "k6 attack"
BASE="$(base_url)"
k6_run attack.js "BASE_URL=$BASE" | tee /tmp/demo13.log || true
step "Verificación"
live_after="$(metric_sum llm-gateway '^llm_tokens_total.*mode="live"')"
assert_eq "$((live_after - live_before))" 0 'increase(llm_tokens_total{mode="live"})'
if [[ -n "${PROM_URL:-}" ]]; then
  # Misma comprobación en Prometheus/Grafana Cloud cuando hay endpoint disponible.
  value="$(curl -sf --get "$PROM_URL/api/v1/query" --data-urlencode 'query=sum(increase(llm_tokens_total{mode="live"}[15m])) or vector(0)' | python -c 'import json,sys;print(int(float(json.load(sys.stdin)["data"]["result"][0]["value"][1])))')"
  assert_eq "$value" 0 "increase() en Prometheus"
fi
assert_contains "$(cat /tmp/demo13.log)" "http_reqs" "resumen de k6"
info "tasks_shed_total: $shed_before -> $(metric_sum orchestrator '^tasks_shed_total')"
if command -v aws >/dev/null && [[ -n "${ASG_NAME:-}" ]]; then
  assert_le "$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" --query 'AutoScalingGroups[0].DesiredCapacity' --output text)" 2 "ASG desired"
fi
demo_summary
