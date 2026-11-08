#!/usr/bin/env bash
# Despliega un ejercicio en un cluster kind efímero y comprueba que responde.
# Corre en el runner de GitHub Actions o en local: nunca toca el cluster del laboratorio.
# Uso: scripts/exercises/kind-smoke.sh <nombre>
set -euo pipefail

readonly NAME="${1:?uso: kind-smoke.sh <nombre>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly CLUSTER="exercise-smoke"
readonly IMAGE="exercise-smoke:${NAME}"
readonly LOCAL_PORT="${LOCAL_PORT:-18080}"
readonly ZERO_SHA="0000000000000000000000000000000000000000"
# En este orden: en Windows, python3 es un acceso directo falso de la Microsoft Store.
PY="$(command -v python || command -v python3)"
readonly PY
WORK_DIR="$(mktemp -d)"
readonly WORK_DIR
# kind cambia el contexto activo: se aísla para no tocar el kubeconfig del usuario.
export KUBECONFIG="$WORK_DIR/kubeconfig"
PF_PID=""

cleanup() {
  if [[ -n "$PF_PID" ]]; then kill "$PF_PID" 2>/dev/null || true; fi
  kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

dump_state() {
  kubectl -n stage get pods -o wide || true
  kubectl -n stage describe pods || true
  kubectl -n stage logs "deploy/$NAME" --tail=50 || true
}

check_route() {
  local route="$1" code
  code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:${LOCAL_PORT}${route}")"
  echo "GET ${route} -> ${code}"
  [[ "$code" == 200 ]]
}

main() {
  docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" "$REPO_ROOT/exercises/$NAME"
  kind create cluster --name "$CLUSTER" --wait 180s
  kind load docker-image "$IMAGE" --name "$CLUSTER"
  kubectl label nodes --all platform.io/pool=apps
  # Mismo nivel de seguridad que el namespace stage del laboratorio.
  kubectl create namespace stage
  kubectl label namespace stage pod-security.kubernetes.io/enforce=restricted

  "$PY" "$REPO_ROOT/scripts/exercises/exercises.py" render "$NAME" \
    --sha "$ZERO_SHA" --out-dir "$WORK_DIR"
  helm template "$NAME" "$REPO_ROOT/kubernetes/charts/agent-service" --namespace stage \
    -f "$WORK_DIR/$NAME/values.yaml" \
    --set image.repository=exercise-smoke --set "image.tag=$NAME" \
    | kubectl -n stage apply -f -

  if ! kubectl -n stage rollout status "deploy/$NAME" --timeout=180s; then
    dump_state
    exit 1
  fi
  kubectl -n stage port-forward "svc/$NAME" "${LOCAL_PORT}:http" >/dev/null &
  PF_PID=$!
  sleep 3
  check_route /healthz
  check_route /readyz
  check_route /
  echo "OK: ${NAME} se despliega y responde"
}

main
