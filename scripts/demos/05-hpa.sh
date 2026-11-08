#!/usr/bin/env bash
# Escenario 5: KEDA/HPA del agente de ejecución sube de réplicas bajo carga.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_cmd docker
step "Carga en segundo plano"
BASE="$(base_url)"
k6_run spike.js "BASE_URL=$BASE" >/tmp/demo05.log 2>&1 &
K6=$!
trap 'kill "$K6" 2>/dev/null || true' EXIT
step "El HPA generado por KEDA escala"
wait_until 300 bash -c "(( \$(kubectl -n apps get deploy executor -o jsonpath='{.status.replicas}') > 1 ))"
assert_ge "$(kubectl -n apps get deploy executor -o jsonpath='{.status.replicas}')" 2 "réplicas de executor"
demo_summary
