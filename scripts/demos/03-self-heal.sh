#!/usr/bin/env bash
# Escenario 3: self-healing. Pod borrado y deriva manual revertida.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/demos/lib.sh"
source "$ROOT/apps/scripts/demo-helpers.sh"
require_cmd kubectl curl
step "Borrado de un pod del gateway"
victim="$(kubectl -n apps get pods -l app.kubernetes.io/name=llm-gateway -o name | head -1)"
kubectl -n apps delete "$victim" --wait=false
wait_until 180 bash -c "[[ \"\$(kubectl -n apps get deploy llm-gateway -o jsonpath='{.status.readyReplicas}')\" == 2 ]]"
step "Deriva manual: selfHeal la revierte"
kubectl -n apps scale deploy llm-gateway --replicas=3
wait_until 180 bash -c "[[ \"\$(kubectl -n apps get deploy llm-gateway -o jsonpath='{.spec.replicas}')\" == 2 ]]"
demo_summary
