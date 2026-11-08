#!/usr/bin/env bash
# infra/scripts/demo-aws.sh: consultas a AWS y Kubernetes comunes a los escenarios 07, 08, 09 y 11.
# Se carga después de scripts/demos/lib.sh. Variables opcionales: ASG_NAME, TG_NAME.
# shellcheck disable=SC2034  # Las constantes las usan los escenarios que cargan este fichero.

readonly ASG_NAME="${ASG_NAME:-agentic-platform-worker}"
readonly TG_NAME="${TG_NAME:-agentic-platform-web}"
readonly DEMO_NAMESPACE="demo-capacity"
readonly DEMO_DEPLOYMENT="capacity-filler"

export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""

asg_desired() {
  aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" \
    --query 'AutoScalingGroups[0].DesiredCapacity' --output text
}

asg_max() {
  aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" \
    --query 'AutoScalingGroups[0].MaxSize' --output text
}

asg_in_service() {
  aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" \
    --query "length(AutoScalingGroups[0].Instances[?LifecycleState=='InService'])" --output text
}

target_group_arn() {
  aws elbv2 describe-target-groups --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text
}

# targets_in_state <estado>: número de targets del NLB en ese estado.
targets_in_state() {
  aws elbv2 describe-target-health --target-group-arn "$(target_group_arn)" \
    --query "length(TargetHealthDescriptions[?TargetHealth.State=='$1'])" --output text
}

worker_nodes() {
  kubectl get nodes -l platform.io/pool=apps -o name
}

ready_worker_count() {
  kubectl get nodes -l platform.io/pool=apps --no-headers | awk '$2 == "Ready"' | wc -l | tr -d ' '
}
