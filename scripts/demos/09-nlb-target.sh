#!/usr/bin/env bash
# Escenario 9: el worker nuevo queda registrado y healthy en el NLB (describe-target-health).
# Un target pasa a healthy cuando su Traefik está listo (externalTrafficPolicy: Local).
# Requiere: credenciales AWS de lectura y el escenario 8 terminado.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../infra/scripts/demo-aws.sh"

all_targets_healthy() { [[ "$(targets_in_state healthy)" == "$(asg_in_service)" ]]; }

main() {
  require_cmd aws

  step "Instancias InService en el ASG"
  local in_service
  in_service="$(asg_in_service)"
  assert_ge "$in_service" 2 "instancias InService"

  step "Esperar a que todas estén healthy en el target group"
  wait_until 300 all_targets_healthy
  aws elbv2 describe-target-health --target-group-arn "$(target_group_arn)" \
    --query 'TargetHealthDescriptions[].[Target.Id,TargetHealth.State]' --output table
  assert_eq "$(targets_in_state healthy)" "$in_service" "targets healthy"

  demo_summary
}

main "$@"
