#!/usr/bin/env bash
# Escenario 11: fin de la carga -> ScaleDown del CA -> instancia terminada, Node y target eliminados.
#
# Tiempos del CA: --scale-down-delay-after-add=5m y --scale-down-unneeded-time=5m, así que
# la bajada tarda unos 10 minutos desde el scale-up. Plan §1.2 #22: el Node debe borrarse
# (cloud-node-lifecycle) para evitar "node password rejected" si se reutiliza la IP.
# Requiere: KUBECONFIG (make tunnel), credenciales AWS de lectura y que la carga haya terminado.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../infra/scripts/demo-aws.sh"

remove_filler() {
  kubectl delete namespace "$DEMO_NAMESPACE" --ignore-not-found --wait=false
}

asg_back_to_one() { [[ "$(asg_desired)" == "1" ]]; }
one_in_service() { [[ "$(asg_in_service)" == "1" ]]; }
one_worker_node() { [[ "$(worker_nodes | wc -l | tr -d ' ')" == "1" ]]; }
one_target_left() { [[ "$(targets_in_state healthy)" == "1" && "$(targets_in_state draining)" == "0" ]]; }

scale_down_event() {
  kubectl get events -A --no-headers 2>/dev/null | grep -Eq 'ScaleDown|ScaledDown|DeletingNode|ScaleDownEmpty'
}

main() {
  require_cmd kubectl aws

  step "Terminar la carga de relleno"
  remove_filler

  step "El Cluster Autoscaler reduce el ASG"
  wait_until 900 asg_back_to_one
  assert_eq "$(asg_desired)" "1" "DesiredCapacity"
  if scale_down_event; then
    log "evento de ScaleDown registrado"
  else
    warn "no se encontró el evento de ScaleDown (los eventos caducan); se valida por el ASG"
  fi

  step "La instancia termina y el CCM borra el Node"
  wait_until 300 one_in_service
  wait_until 300 one_worker_node
  kubectl get nodes -o wide

  step "El target se deregistra del NLB"
  wait_until 180 one_target_left
  assert_eq "$(targets_in_state healthy)" "1" "targets healthy"

  demo_summary
}

main "$@"
