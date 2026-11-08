#!/usr/bin/env bash
# Utilidades de las demos de la flota (se carga después de scripts/demos/lib.sh).
# Las imágenes son distroless: sin shell, así que /metrics se lee por port-forward.
NS="${NS:-apps}"
K="${KUBECTL:-kubectl}"
HELPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export K6_IMAGE="${K6_IMAGE:-grafana/k6:1.8.2}"

# scrape <pod> <puerto-local>: imprime /metrics de un pod.
scrape() {
  local pod="$1" port="$2" pf
  "$K" -n "$NS" port-forward "pod/$pod" "$port:8000" >/dev/null 2>&1 &
  pf=$!
  sleep 2
  curl -sf --max-time 5 "http://127.0.0.1:$port/metrics" || true
  kill "$pf" 2>/dev/null || true
  wait "$pf" 2>/dev/null || true
}

# metric_sum <app> <regex>: suma una serie en todas las réplicas de un Deployment.
metric_sum() {
  local app="$1" re="$2" port=19100 pod total=0 v
  for pod in $("$K" -n "$NS" get pods -l "app.kubernetes.io/name=$app" -o name | cut -d/ -f2); do
    v="$(scrape "$pod" "$port" | grep -E "$re" | awk '{s+=$NF} END {printf "%d", s}')"
    total=$((total + ${v:-0}))
    port=$((port + 1))
  done
  echo "$total"
}

# with_orchestrator <puerto> <cmd...>: ejecuta cmd con BASE_URL apuntando al orquestador.
pf_service() {
  local svc="$1" local_port="$2"
  "$K" -n "$NS" port-forward "svc/$svc" "$local_port:8000" >/dev/null 2>&1 &
  echo $!
}

# base_url: NLB si existe NLB_URL; si no, port-forward al orquestador (perfil local).
base_url() {
  if [[ -n "${NLB_URL:-}" ]]; then echo "${NLB_URL%/}"; return; fi
  pf_service orchestrator 18000 >/dev/null
  sleep 2
  echo "http://127.0.0.1:18000"
}

# k6_run <script> [VAR=valor...]: ejecuta un escenario con la imagen fijada.
k6_run() {
  local script="$1"; shift
  local envs=() v host_dir
  for v in "$@"; do envs+=(-e "$v"); done
  # En Git Bash, MSYS convertiría /k6/... en C:/Program Files/Git/k6/...
  host_dir="$(cd "$HELPER_DIR/../loadgen/k6" && { pwd -W 2>/dev/null || pwd; })"
  MSYS_NO_PATHCONV=1 docker run --rm --network host -v "$host_dir:/k6:ro" "${envs[@]}" "$K6_IMAGE" run "/k6/$script"
}
