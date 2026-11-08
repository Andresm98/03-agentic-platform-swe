#!/usr/bin/env bash
# Escenario 12: Grafana Cloud devuelve series y logs recientes del cluster.
#
# Variables (token de solo lectura, distinto del token de escritura de Alloy):
#   GRAFANA_PROM_QUERY_URL  p. ej. https://prometheus-prod-XX.grafana.net/api/prom
#   GRAFANA_PROM_USER       instancia de Prometheus
#   GRAFANA_LOKI_QUERY_URL  p. ej. https://logs-prod-XXX.grafana.net
#   GRAFANA_LOKI_USER       instancia de Loki
#   GRAFANA_READ_TOKEN      token con metrics:read y logs:read
# Requiere: curl y jq.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly CLUSTER_SELECTOR='cluster="agentic-platform"'

# prom_series <promql>: número de series devueltas por la consulta.
prom_series() {
  curl -sSf -G -u "$GRAFANA_PROM_USER:$GRAFANA_READ_TOKEN" \
    --data-urlencode "query=$1" "$GRAFANA_PROM_QUERY_URL/api/v1/query" | jq '.data.result | length'
}

# loki_lines <logql>: líneas de log de los últimos 15 minutos.
loki_lines() {
  local end start
  end="$(date +%s)"
  start=$((end - 900))
  curl -sSf -G -u "$GRAFANA_LOKI_USER:$GRAFANA_READ_TOKEN" \
    --data-urlencode "query=$1" --data-urlencode "start=${start}000000000" --data-urlencode "end=${end}000000000" \
    --data-urlencode "limit=20" "$GRAFANA_LOKI_QUERY_URL/loki/api/v1/query_range" \
    | jq '[.data.result[].values | length] | add // 0'
}

assert_has_series() {
  local count
  count="$(prom_series "$1")"
  assert_ge "$count" 1 "$2 ($1)"
}

main() {
  require_cmd curl jq
  require_env GRAFANA_PROM_QUERY_URL GRAFANA_PROM_USER GRAFANA_LOKI_QUERY_URL GRAFANA_LOKI_USER GRAFANA_READ_TOKEN

  step "Métricas del cluster en Grafana Cloud"
  assert_has_series "kube_node_info{$CLUSTER_SELECTOR}" "kube-state-metrics"
  assert_has_series "traefik_service_requests_total{$CLUSTER_SELECTOR}" "borde (Traefik)"
  assert_has_series "nats_consumer_num_pending{$CLUSTER_SELECTOR}" "cola JetStream"
  assert_has_series "llm_tokens_total{$CLUSTER_SELECTOR}" "tokens del LLM"
  assert_has_series "cluster_autoscaler_nodes_count{$CLUSTER_SELECTOR}" "Cluster Autoscaler"

  step "Logs de la flota en Grafana Cloud"
  local lines
  lines="$(loki_lines '{namespace="apps"}')"
  assert_ge "$lines" 1 "líneas de log en los últimos 15 minutos"

  demo_summary
}

main "$@"
