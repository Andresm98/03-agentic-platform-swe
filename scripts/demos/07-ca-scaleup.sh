#!/usr/bin/env bash
# Escenario 7: el Cluster Autoscaler lanza una EC2 (evidencia: TriggeredScaleUp y DesiredCapacity=2).
#
# Si USE_EXISTING_LOAD=1, se usa la carga de los escenarios 4-6 (Pending de agentes). Si no,
# crea un Deployment de pausa cuyos requests no caben en un worker. El escenario 11 lo borra.
# Requiere: KUBECONFIG (make tunnel), credenciales AWS de lectura, kubectl y aws.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../infra/scripts/demo-aws.sh"

readonly FILLER_REPLICAS="${FILLER_REPLICAS:-3}"
readonly FILLER_CPU="${FILLER_CPU:-900m}"

create_filler() {
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $DEMO_NAMESPACE
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $DEMO_DEPLOYMENT
  namespace: $DEMO_NAMESPACE
spec:
  replicas: $FILLER_REPLICAS
  selector:
    matchLabels: { app: $DEMO_DEPLOYMENT }
  template:
    metadata:
      labels: { app: $DEMO_DEPLOYMENT }
    spec:
      automountServiceAccountToken: false
      nodeSelector:
        platform.io/pool: apps
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.10
          resources:
            requests: { cpu: "$FILLER_CPU", memory: 32Mi }
          securityContext:
            runAsNonRoot: true
            runAsUser: 65535
            allowPrivilegeEscalation: false
            capabilities: { drop: [ALL] }
EOF
}

pending_pods() {
  kubectl get pods -A --field-selector=status.phase=Pending --no-headers 2>/dev/null | wc -l | tr -d ' '
}

has_pending() { (($(pending_pods) > 0)); }

scale_up_event() {
  kubectl get events -A --field-selector reason=TriggeredScaleUp --no-headers 2>/dev/null | grep -q .
}

asg_scaled() { [[ "$(asg_desired)" == "2" ]]; }

main() {
  require_cmd kubectl aws

  step "Estado inicial del ASG"
  assert_eq "$(asg_desired)" "1" "DesiredCapacity inicial"
  assert_eq "$(asg_max)" "2" "MaxSize (techo de 3 EC2 con el control plane)"

  step "Generar Pending"
  if [[ "${USE_EXISTING_LOAD:-0}" == "1" ]]; then
    info "se usa la carga existente (USE_EXISTING_LOAD=1)"
  else
    create_filler
  fi
  wait_until 120 has_pending

  step "El Cluster Autoscaler reacciona"
  wait_until 240 scale_up_event
  kubectl get events -A --field-selector reason=TriggeredScaleUp --no-headers | tail -3

  step "El ASG sube a 2"
  wait_until 180 asg_scaled
  assert_eq "$(asg_desired)" "2" "DesiredCapacity tras el scale-up"

  demo_summary
}

main "$@"
