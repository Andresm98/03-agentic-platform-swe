#!/usr/bin/env bash
# cost-check.sh: comprueba con describe-* directos que no queda nada facturable del lab
# (ADR-0001 §5). Sale con 1 si encuentra algo; 0 si está limpio.
# Comprueba: EC2, ASG, NLB/ALB, target groups, volúmenes EBS, EIPs, ENIs, VPC, launch templates.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

FOUND=0

# report <tipo> <ids...>: anota recursos encontrados.
report() {
  local kind="$1"
  shift
  local ids="$*"
  if [[ -n "${ids// /}" && "$ids" != "None" ]]; then
    warn "QUEDA $kind: $ids"
    FOUND=1
  else
    log "ok: sin $kind"
  fi
}

project_filter() { printf '%s' "Name=tag:Project,Values=$PROJECT_TAG"; }

check_instances() {
  report "instancias EC2" "$(aws ec2 describe-instances --filters "$(project_filter)" \
    "Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down" \
    --query 'Reservations[].Instances[].InstanceId' --output text)"
}

check_asgs() {
  report "Auto Scaling groups" "$(aws autoscaling describe-auto-scaling-groups \
    --query "AutoScalingGroups[?Tags[?Key=='Project' && Value=='$PROJECT_TAG']].AutoScalingGroupName" --output text)"
}

# Los LB y TG no admiten filtro por tag en describe-*: se buscan por prefijo de nombre
# (todos los del lab se llaman agentic-platform-*).
check_load_balancers() {
  report "load balancers" "$(aws elbv2 describe-load-balancers \
    --query "LoadBalancers[?starts_with(LoadBalancerName, '$PROJECT_TAG')].LoadBalancerName" --output text)"
  report "target groups" "$(aws elbv2 describe-target-groups \
    --query "TargetGroups[?starts_with(TargetGroupName, '$PROJECT_TAG')].TargetGroupName" --output text)"
}

check_volumes() {
  report "volúmenes EBS" "$(aws ec2 describe-volumes --filters "$(project_filter)" \
    --query 'Volumes[].VolumeId' --output text)"
}

check_eips() {
  report "Elastic IPs" "$(aws ec2 describe-addresses --filters "$(project_filter)" \
    --query 'Addresses[].AllocationId' --output text)"
}

check_network() {
  local vpcs
  vpcs="$(aws ec2 describe-vpcs --filters "$(project_filter)" --query 'Vpcs[].VpcId' --output text)"
  report "VPC" "$vpcs"
  report "ENIs etiquetadas" "$(aws ec2 describe-network-interfaces --filters "$(project_filter)" \
    --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)"
  local vpc
  for vpc in $vpcs; do
    report "ENIs en $vpc" "$(aws ec2 describe-network-interfaces --filters "Name=vpc-id,Values=$vpc" \
      --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)"
  done
}

check_launch_templates() {
  report "launch templates" "$(aws ec2 describe-launch-templates --filters "$(project_filter)" \
    --query 'LaunchTemplates[].LaunchTemplateName' --output text)"
}

main() {
  require_cmd aws
  log "cost-check en la cuenta $(aws_account_id), región $AWS_REGION"
  check_instances
  check_asgs
  check_load_balancers
  check_volumes
  check_eips
  check_network
  check_launch_templates
  if ((FOUND)); then
    die "quedan recursos del lab: revisa la salida (terraform destroy incompleto o recursos manuales)"
  fi
  log "cost-check OK: no queda nada facturable del lab"
}

main "$@"
