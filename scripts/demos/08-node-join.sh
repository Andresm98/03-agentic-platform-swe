#!/usr/bin/env bash
# Escenario 8: la EC2 nueva se une a K3s (evidencia: nodo Ready, providerID aws:/// y sin taint uninitialized).
# Requiere: KUBECONFIG (make tunnel) y el escenario 7 en curso.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../infra/scripts/demo-aws.sh"

two_workers_ready() { [[ "$(ready_worker_count)" == "2" ]]; }

assert_node_identity() {
  local node="$1" name provider taints
  name="${node#node/}"
  provider="$(kubectl get "$node" -o jsonpath='{.spec.providerID}')"
  taints="$(kubectl get "$node" -o jsonpath='{.spec.taints[*].key}')"
  assert_contains "$provider" "aws:///" "providerID de $name"
  assert_contains "$name" ".ec2.internal" "nombre de nodo = private DNS"
  if [[ "$taints" == *"node.cloudprovider.kubernetes.io/uninitialized"* ]]; then
    die "$name conserva el taint uninitialized: el CCM no lo ha inicializado"
  fi
  log "$name: providerID=$provider"
}

main() {
  require_cmd kubectl

  step "Esperar a los dos workers Ready"
  wait_until 420 two_workers_ready
  kubectl get nodes -o wide

  step "Identidad de cada worker (ADR-0002 §1)"
  local node
  while read -r node; do
    assert_node_identity "$node"
  done < <(worker_nodes)

  demo_summary
}

main "$@"
