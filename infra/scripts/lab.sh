#!/usr/bin/env bash
# lab.sh up|down: levanta o destruye el lab (L0) desde local. Es el respaldo de lab.yml.
#   up   -> terraform plan + apply de envs/lab (pide confirmación salvo AUTO_APPROVE=1)
#   down -> terraform destroy + cost-check.sh (sale != 0 si queda algo facturable)
# Requiere: TF_STATE_BUCKET o envs/lab/backend.hcl, y envs/lab/terraform.tfvars.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  echo "uso: $0 up|down" >&2
  exit 2
}

preflight() {
  require_cmd terraform aws
  [[ -f "$INFRA_LAB_DIR/terraform.tfvars" ]] \
    || die "falta $INFRA_LAB_DIR/terraform.tfvars (copia terraform.tfvars.example)"
  log "cuenta AWS $(aws_account_id), región $AWS_REGION"
  tf_lab_init
}

lab_up() {
  preflight
  tf_lab plan -input=false -out=lab.tfplan
  confirm "¿Crear/actualizar el lab? (~0.2 USD/h mientras exista)"
  tf_lab apply -input=false lab.tfplan
  rm -f "$INFRA_LAB_DIR/lab.tfplan"
  log "lab arriba. NLB: http://$(lab_output nlb_dns_name)/  (los targets tardan unos minutos en estar healthy)"
  log "siguiente: make tunnel"
}

lab_down() {
  preflight
  confirm "¿Destruir el lab completo?"
  tf_lab destroy -input=false -auto-approve
  log "destroy terminado; comprobando recursos huérfanos"
  bash "$(dirname "${BASH_SOURCE[0]}")/cost-check.sh"
}

main() {
  (($# == 1)) || usage
  case "$1" in
    up) lab_up ;;
    down) lab_down ;;
    *) usage ;;
  esac
}

main "$@"
