#!/usr/bin/env bash
# tunnel.sh: acceso al API server sin SSH ni 6443 público (plan §1.2 #19).
#  1. Descarga /etc/rancher/k3s/k3s.yaml del CP con ssm send-command -> .lab/kubeconfig (0600).
#     El kubeconfig de K3s ya apunta a https://127.0.0.1:6443 y su certificado incluye 127.0.0.1.
#  2. Abre un port forwarding de Session Manager localhost:6443 -> CP:6443 (primer plano).
# Uso: make tunnel; en otra terminal: export KUBECONFIG=.lab/kubeconfig
# Variables: LOCAL_PORT (6443), CP_INSTANCE_ID (si no, se busca por tags).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly LOCAL_PORT="${LOCAL_PORT:-6443}"
readonly KUBECONFIG_OUT="$INFRA_STATE_DIR/kubeconfig"

find_control_plane() {
  if [[ -n "${CP_INSTANCE_ID:-}" ]]; then
    printf '%s' "$CP_INSTANCE_ID"
    return 0
  fi
  local id
  id="$(aws ec2 describe-instances \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" "Name=tag:platform.io/role,Values=control-plane" \
    "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].InstanceId | [0]' --output text)"
  [[ -n "$id" && "$id" != "None" ]] || die "no hay control plane en ejecución (¿make up?)"
  printf '%s' "$id"
}

fetch_kubeconfig() {
  local instance="$1" cmd_id status
  cmd_id="$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
    --comment "agentic: leer kubeconfig" \
    --parameters 'commands=["cat /etc/rancher/k3s/k3s.yaml"]' \
    --query Command.CommandId --output text)" || die "ssm send-command falló (¿agente SSM online?)"
  for _ in $(seq 1 30); do
    status="$(aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$instance" \
      --query Status --output text 2>/dev/null || echo Pending)"
    case "$status" in
      Success) break ;;
      Failed | Cancelled | TimedOut) die "la lectura del kubeconfig terminó en $status" ;;
    esac
    sleep 2
  done
  [[ "$status" == "Success" ]] || die "timeout esperando el kubeconfig"
  mkdir -p "$INFRA_STATE_DIR"
  (
    umask 077
    aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$instance" \
      --query StandardOutputContent --output text \
      | sed "s#https://127.0.0.1:6443#https://127.0.0.1:$LOCAL_PORT#" >"$KUBECONFIG_OUT"
  )
  grep -q 'certificate-authority-data' "$KUBECONFIG_OUT" || die "kubeconfig vacío o incompleto"
  log "kubeconfig en $KUBECONFIG_OUT (export KUBECONFIG=$KUBECONFIG_OUT)"
}

open_tunnel() {
  local instance="$1"
  log "túnel localhost:$LOCAL_PORT -> $instance:6443 (Ctrl+C para cerrar)"
  aws ssm start-session --target "$instance" --document-name AWS-StartPortForwardingSession \
    --parameters "{\"portNumber\":[\"6443\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}"
}

main() {
  require_cmd aws session-manager-plugin
  local instance
  instance="$(find_control_plane)"
  fetch_kubeconfig "$instance"
  open_tunnel "$instance"
}

main "$@"
