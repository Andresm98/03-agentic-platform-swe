#!/usr/bin/env bash
# Escenario 2: un commit promociona la imagen y Argo CD la despliega.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
require_env EXPECTED_SHA
step "Argo CD refleja el commit"
wait_until 300 bash -c "kubectl -n argocd get application fleet-orchestrator -o jsonpath='{.status.sync.revision}' | grep -q ."
step "El pod corre la imagen :$EXPECTED_SHA"
wait_until 300 bash -c "kubectl -n apps get deploy orchestrator -o jsonpath='{.spec.template.spec.containers[0].image}' | grep -q ':$EXPECTED_SHA$'"
rev="$(kubectl -n argocd get application fleet-orchestrator -o jsonpath='{.status.history[-1].revision}')"
assert_ge "${#rev}" 7 "longitud de la revisión en el historial de Argo"
demo_summary
