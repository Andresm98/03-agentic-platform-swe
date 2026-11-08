#!/usr/bin/env bash
# bootstrap.sh: crea la capa persistente L-1 (ADR-0001 §1) UNA sola vez, desde local y con
# credenciales de administrador: bucket S3 de estado, AWS Budget, OIDC de GitHub,
# agentic-boundary y los roles agentic-github-*.
#
# Requiere: infra/terraform/bootstrap/terraform.tfvars (ver terraform.tfvars.example).
# Uso: make bootstrap   (AUTO_APPROVE=1 para no preguntar)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  require_cmd terraform aws
  [[ -f "$INFRA_BOOTSTRAP_DIR/terraform.tfvars" ]] \
    || die "falta $INFRA_BOOTSTRAP_DIR/terraform.tfvars (copia terraform.tfvars.example)"

  local account
  account="$(aws_account_id)"
  log "cuenta AWS $account, región $AWS_REGION"

  terraform -chdir="$INFRA_BOOTSTRAP_DIR" init -input=false
  terraform -chdir="$INFRA_BOOTSTRAP_DIR" plan -input=false -out=bootstrap.tfplan
  confirm "¿Aplicar la capa persistente en la cuenta $account?"
  terraform -chdir="$INFRA_BOOTSTRAP_DIR" apply -input=false bootstrap.tfplan
  rm -f "$INFRA_BOOTSTRAP_DIR/bootstrap.tfplan"

  log "hecho. Siguientes pasos:"
  terraform -chdir="$INFRA_BOOTSTRAP_DIR" output
  cat >&2 <<'EOF'
  1. GitHub > Settings > Environments: crear 'lab' (con revisores), 'lab-reaper' (sin
     revisores, solo rama main) y 'observability'. En cada uno, variable AWS_ROLE_ARN
     con el rol correspondiente de github_role_arns, y TF_STATE_BUCKET con state_bucket.
  2. infra/terraform/envs/lab/terraform.tfvars: permissions_boundary_arn = permissions_boundary_arn.
  3. make seed-secrets
  4. Guarda infra/terraform/bootstrap/terraform.tfstate fuera de Git (estado local).
EOF
}

main "$@"
