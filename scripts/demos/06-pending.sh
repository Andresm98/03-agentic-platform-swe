#!/usr/bin/env bash
# Escenario 6: aparecen pods Pending por CPU insuficiente.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_cmd docker
step "Carga sostenida"
BASE="$(base_url)"
k6_run ramp.js "BASE_URL=$BASE" >/tmp/demo06.log 2>&1 &
K6=$!
trap 'kill "$K6" 2>/dev/null || true' EXIT
step "Evento FailedScheduling"
wait_until 420 bash -c "kubectl -n apps get events --field-selector reason=FailedScheduling -o jsonpath='{.items[*].message}' | grep -q 'Insufficient cpu'"
demo_summary
