#!/usr/bin/env bash
# Escenario 4: aumento de tráfico con k6 (rampa), siempre contra fake-llm.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_cmd docker
step "Rampa de k6"
BASE="$(base_url)"
k6_run ramp.js "BASE_URL=$BASE"
step "Sin tokens live"
assert_eq "$(metric_sum llm-gateway '^llm_tokens_total.*mode="live"')" 0 "tokens live"
demo_summary
