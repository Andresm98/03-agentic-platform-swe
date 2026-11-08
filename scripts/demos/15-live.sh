#!/usr/bin/env bash
# Escenario 15: demo live con X-Demo-Token. Requiere LLM_GLOBAL_MODE=live en Git. Gasta dinero real.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_env DEMO_TOKEN
[[ "${CONFIRM_LIVE:-}" == yes ]] || die "esta demo llama a OpenAI: ejecútala con CONFIRM_LIVE=yes"
step "Tarea live"
BASE="$(base_url)"
before="$(metric_sum llm-gateway '^llm_tokens_total.*mode="live"')"
resp="$(curl -sf -X POST "$BASE/tasks" -H 'content-type: application/json' -H "X-Demo-Token: $DEMO_TOKEN" -d '{"goal":"Resume la elasticidad de la plataforma","complexity":1}')"
assert_contains "$resp" '"mode":"live"' "modo admitido"
id="$(echo "$resp" | python -c 'import json,sys;print(json.load(sys.stdin)["task_id"])')"
wait_until 180 bash -c "curl -s '$BASE/tasks/$id' | grep -qE '\"status\":\"(completed|failed)\"'"
after="$(metric_sum llm-gateway '^llm_tokens_total.*mode="live"')"
assert_ge "$((after - before))" 1 "tokens live consumidos"
info "Presupuesto: $(metric_sum llm-gateway '^llm_budget_remaining') USD (entero)"
step "Degradación"
info "Para comprobar degraded=true: fija LLM_BUDGET_USD a un valor mínimo en Git y repite la tarea."
if [[ -n "${EXPECT_DEGRADED:-}" ]]; then
  assert_contains "$(curl -s "$BASE/tasks/$id")" '"degraded":true' "tarea degradada"
fi
demo_summary
