#!/usr/bin/env bash
# k3d.sh up|down: perfil local de costo cero (Fase 0, ADR-0001 §5 "local primero").
#
# Topología equivalente a AWS: 1 server con el taint CriticalAddonsOnly (plataforma) y
# 2 agents etiquetados platform.io/pool=apps (flota y DaemonSets). Mismo Argo CD
# (kubernetes/bootstrap/argocd.yaml) y mismos charts; root-app sobre gitops/clusters/local-k3d.
#
# Diferencias documentadas respecto a aws-lab:
#   - Sin AWS CCM (no hay EC2), sin Cluster Autoscaler (nodos fijos) y sin ESO-AWS:
#     se crea un ClusterSecretStore "aws-ssm" de tipo fake con valores ALEATORIOS
#     generados aquí (nunca reales) y las mismas rutas que CONTRACTS §6.
#   - Sin k8s-monitoring (Grafana Cloud) ni Argo CD Notifications (GitHub App).
#   - Argo CD lee de GitHub: los cambios locales deben estar en una rama remota
#     (GITOPS_REVISION=<rama> cambia la revisión de root; las hijas siguen en main).
#   - La imagen rancher/k3s viene de Docker Hub (solo en local; los nodos de AWS no la usan).
#
# Acceso: Traefik en http://localhost:${LOCAL_HTTP_PORT:-8080}/ ; Argo CD con
#   kubectl -n argocd port-forward svc/argo-cd-argocd-server 8081:80
set -euo pipefail

readonly CLUSTER="${K3D_CLUSTER:-agentic-local}"
readonly K3S_IMAGE="rancher/k3s:v1.35.10-k3s1" # misma versión que AWS (pins.tf)
readonly LOCAL_HTTP_PORT="${LOCAL_HTTP_PORT:-8080}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() {
  printf '[%s] ERROR: %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2
  exit 1
}

require_cmd() {
  local c
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || die "falta $c (k3d v5.9.0, kubectl, docker, python3)"; done
}

# find_python: python3 o python que funcione (en Windows "python3" puede ser el alias de la Store).
find_python() {
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import json, secrets' >/dev/null 2>&1; then
      PYTHON="$c"
      return 0
    fi
  done
  die "no hay un Python 3 operativo (python3/python)"
}

# wait_for <segundos> <descripción> <cmd...>
wait_for() {
  local timeout="$1" what="$2" waited=0
  shift 2
  until "$@" >/dev/null 2>&1; do
    ((waited >= timeout)) && die "timeout ($timeout s) esperando: $what"
    sleep 5
    waited=$((waited + 5))
  done
  log "listo: $what"
}

create_cluster() {
  if k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
    log "el cluster $CLUSTER ya existe"
    return 0
  fi
  k3d cluster create "$CLUSTER" \
    --image "$K3S_IMAGE" \
    --servers 1 --agents 2 \
    --k3s-arg "--disable=traefik,servicelb@server:0" \
    --k3s-arg "--node-taint=CriticalAddonsOnly=true:NoExecute@server:0" \
    --k3s-arg "--node-label=platform.io/pool=apps@agent:*" \
    --k3s-arg "--node-label=platform.io/role=worker@agent:*" \
    --port "$LOCAL_HTTP_PORT:30080@loadbalancer" \
    --wait
}

install_argocd() {
  kubectl apply -f "$REPO_ROOT/kubernetes/bootstrap/argocd.yaml"
  wait_for 600 "CRD de Argo CD" kubectl get crd applications.argoproj.io
}

# fake_store_manifest: ClusterSecretStore aws-ssm (provider fake) con secretos aleatorios.
fake_store_manifest() {
  "$PYTHON" - <<'PY'
import json, secrets
r = lambda: "s" + secrets.token_hex(24)  # NATS rechaza contraseñas tipo 12-abc
p = "/agentic-platform/k8s"
data = {
    f"{p}/openai-api-key": "sk-local-fake-" + r(),  # nunca una key real: el gateway usa fake-llm
    f"{p}/langsmith-api-key": "ls-local-fake-" + r(),
    f"{p}/demo-token": r(),
    f"{p}/redis-password": r(),
    f"{p}/grafana-cloud": json.dumps({k: "http://disabled.local" if k.endswith("url") else "local"
                                      for k in ("prom_url", "prom_user", "loki_url", "loki_user",
                                                "otlp_url", "otlp_user", "token")}),
    f"{p}/github-app": json.dumps({"appID": "0", "installationID": "0", "privateKey": "disabled"}),
}
for svc in ("orchestrator", "researcher", "analyst", "executor", "llm-gateway", "fake-llm"):
    data[f"{p}/nats/{svc}-password"] = r()
store = {
    "apiVersion": "external-secrets.io/v1",
    "kind": "ClusterSecretStore",
    "metadata": {"name": "aws-ssm", "labels": {"agentic.io/cluster": "local-k3d"}},
    "spec": {"provider": {"fake": {"data": [{"key": k, "value": v} for k, v in data.items()]}}},
}
print(json.dumps(store))
PY
}

install_fake_secret_store() {
  wait_for 900 "CRD ClusterSecretStore (ESO)" kubectl get crd clustersecretstores.external-secrets.io
  if kubectl get clustersecretstore aws-ssm >/dev/null 2>&1; then
    log "ClusterSecretStore aws-ssm ya existe (se conservan sus valores)"
    return 0
  fi
  local manifest
  manifest="$(fake_store_manifest)"
  [[ -n "$manifest" ]] || die "no se pudo generar el ClusterSecretStore fake"
  printf '%s' "$manifest" | kubectl apply -f -
}

install_root_app() {
  local revision="${GITOPS_REVISION:-main}"
  sed "s#targetRevision: main#targetRevision: $revision#" \
    "$REPO_ROOT/gitops/clusters/local-k3d/root-app.yaml" | kubectl apply -f -
  log "root (local-k3d) aplicada sobre la revisión $revision"
}

cmd_up() {
  require_cmd k3d kubectl docker
  find_python
  create_cluster
  kubectl config use-context "k3d-$CLUSTER" >/dev/null
  install_argocd
  install_root_app
  install_fake_secret_store
  log "Argo CD sincroniza la plataforma (kubectl -n argocd get applications -w)"
  log "contraseña admin: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
  log "Traefik: http://localhost:$LOCAL_HTTP_PORT/"
}

cmd_down() {
  require_cmd k3d
  k3d cluster delete "$CLUSTER"
}

main() {
  case "${1:-}" in
    up) cmd_up ;;
    down) cmd_down ;;
    *)
      echo "uso: $0 up|down" >&2
      exit 2
      ;;
  esac
}

main "$@"
