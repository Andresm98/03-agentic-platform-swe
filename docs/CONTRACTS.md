# Contratos de implementación entre capas

Fuente única de nombres, rutas e interfaces compartidas. Si un valor de aquí cambia, cambia en todas las capas.
Diseño: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ADR-0001](adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md) · [ADR-0002](adrs/0002-identidad-credenciales-y-elasticidad.md)

## 1. Propiedad de directorios (quién escribe qué)

| Equipo | Escribe en | No toca |
|---|---|---|
| **S — Scaffolding** | Raíz (`README.md`, `Makefile`, `.gitignore`, `.gitattributes`, `.editorconfig`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `LICENSE`), `.github/dependabot.yml`, `.github/CODEOWNERS`, `docs/versions.md`, `docs/runbook.md`, `docs/architecture.md`, `docs/validation-log.md`, `scripts/demos/lib.sh`, `scripts/demos/README.md`, `.gitkeep` en directorios vacíos | Contenido de los directorios de P y A |
| **P — Infra + Plataforma** | `infra/**`, `kubernetes/bootstrap/**`, `gitops/root-app.yaml`, `gitops/platform/**`, `gitops/clusters/**`, `gitops/argocd-apps/platform-*.yaml`, `observability/**`, `scripts/local/**`, `scripts/demos/0{7,8,9}-*.sh`, `scripts/demos/1{1,2}-*.sh`, `.github/workflows/{lab,lab-reaper,observability,mirror-images,_iac-scan}.yml`, `platform-images.lock`, `docs/validation/platform.md` | `apps/**`, `kubernetes/charts/**`, `gitops/apps/**` |
| **A — Flota agéntica + CI** | `apps/**`, `kubernetes/charts/**`, `gitops/apps/**`, `gitops/argocd-apps/fleet-*.yaml`, `scripts/demos/0{1,2,3,4,5,6}-*.sh`, `scripts/demos/1{0,3,4,5}-*.sh`, `.github/workflows/{main,_ci,_images,_gitops-promote,post-deploy}.yml`, `docs/validation/fleet.md` | `infra/**`, `gitops/platform/**`, `kubernetes/bootstrap/**` |
| **Ejercicios (`stage`)** | `exercises/**`, `scripts/exercises/**`, `gitops/stage/**` (solo CI), `gitops/platform/stage/**`, `gitops/argocd-apps/{stage-*,platform-stage}.yaml`, `.github/workflows/exercises.yml` | Plataforma y flota |

## 2. Identificadores globales

| Clave | Valor |
|---|---|
| Proyecto / prefijo AWS | `agentic-platform` / recursos IAM `agentic-*` |
| Región | `us-east-1` |
| Repo GitHub (**confirmado**) | `https://github.com/Andresm98/03-agentic-platform-swe` (rama `main`); OIDC `sub` = `repo:Andresm98@41342993/03-agentic-platform-swe@1449959239:environment:lab` |
| Registry | `ghcr.io/andresm98/agentic-platform/<servicio>:<git-sha>` |
| Mirror de plataforma | `ghcr.io/andresm98/agentic-platform/mirror/<imagen>@sha256:<digest>` |
| Servicios de la flota (`app-id` Dapr = nombre) | `orchestrator`, `researcher`, `analyst`, `executor`, `llm-gateway`, `fake-llm` |
| Puerto HTTP de cada servicio | `8000` (`/healthz`, `/readyz`, `/metrics`) |
| Tags AWS obligatorias | `Project=agentic-platform`, `Lifecycle=ephemeral`, `Owner=<var>`; `kubernetes.io/cluster/agentic-platform=owned`; ASG: `k8s.io/cluster-autoscaler/enabled=true`, `k8s.io/cluster-autoscaler/agentic-platform=owned` |

## 3. Namespaces

`argocd`, `kube-system` (CCM, CA), `keda`, `external-secrets`, `traefik`, `nats`, `data` (Redis), `dapr-system`, `monitoring` (Alloy, kube-state-metrics, node-exporter), `stage` (ejercicios de estudiantes), `apps` (flota completa), `llm` no existe: el gateway y fake-llm viven en `apps`.

## 4. Planificación en nodos

- Control plane: taint `CriticalAddonsOnly=true:NoExecute`, selector `node-role.kubernetes.io/control-plane: "true"`. Todo lo de plataforma + `fake-llm` + NATS + Redis + Dapr control plane.
- Workers: label `platform.io/pool: apps`. Agentes, `llm-gateway`, DaemonSets (Traefik, Alloy logs, node-exporter).

## 5. Endpoints internos (P los expone, A los consume)

| Recurso | Endpoint |
|---|---|
| NATS cliente | `nats://nats.nats.svc.cluster.local:4222` |
| NATS monitorización (KEDA) | `http://nats.nats.svc.cluster.local:8222` |
| Redis (estado de Dapr Workflow) | `redis.data.svc.cluster.local:6379`, contraseña en Secret `redis-auth` clave `password` (namespace `data`; A crea su propio ExternalSecret en `apps`) |
| OTLP (trazas) | `alloy-otlp.monitoring.svc.cluster.local:4317` (gRPC) / `:4318` (HTTP) |
| Scraping de métricas | Annotations de pod `prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"`, `prometheus.io/path: /metrics` |
| Traefik | `ingressClassName: traefik`; middlewares `rate-limit` y `body-limit` en ns `traefik` → annotation `traefik.ingress.kubernetes.io/router.middlewares: traefik-rate-limit@kubernetescrd,traefik-body-limit@kubernetescrd` |
| ESO | `ClusterSecretStore` llamado `aws-ssm` (lo crea P) |

## 6. Parámetros SSM (`SecureString`, capa persistente, creados por `infra/scripts/seed-secrets.sh`)

| Ruta | Consumidor |
|---|---|
| `/agentic-platform/k8s/openai-api-key` | `llm-gateway` |
| `/agentic-platform/k8s/demo-token` | `orchestrator` |
| `/agentic-platform/k8s/grafana-cloud` (JSON: urls, usuarios, token) | Alloy |
| `/agentic-platform/k8s/redis-password` | Redis (P) y sidecars Dapr (A) |
| `/agentic-platform/k8s/nats/<servicio>-password` (uno por servicio de la flota) | NATS (P) y componentes Dapr / gateway (A) |
| `/agentic-platform/k8s/github-app` (JSON: appID, installationID, privateKey) | Argo CD Notifications |
| `/agentic-platform/k8s/langsmith-api-key` (**obligatorio**) | `llm-gateway` (adaptador de telemetría LangSmith, activado por defecto) |
| `/agentic-platform/cluster/join-token` | K3s (lo escribe el control plane; Terraform crea el recurso con `value_wo`, y el token no llega al estado) |

## 7. Mensajería

- Stream JetStream `TASKS`, subjects `tasks.>` y `agent.>`, file storage, `max_age` 24 h, `max_msgs`/`max_bytes` con `discard=new`; DLQ `tasks.dead`.
- KV buckets: `llm-budget` (gateway). El estado de workflows va en Redis, no en KV.
- Topics: `tasks.created`, `tasks.completed`, `tasks.evaluated`, `agent.research.requested|completed`, `agent.analysis.requested|completed`, `agent.execution.requested|completed`.
- Durable consumers (uno por agente, creados por un Job de A antes de los Deployments): `orchestrator`, `researcher`, `analyst`, `executor`. KEDA escala sobre ellos.
- Componente Dapr de pub/sub: `pubsub` (tipo `pubsub.jetstream`); de estado: `workflowstore` (tipo `state.redis`, `actorStateStore: "true"`). Ambos los define A en `gitops/apps/dapr/`.

## 8. App-of-apps

`gitops/root-app.yaml` (P) apunta al directorio `gitops/argocd-apps/` (recurse). Allí P deja `platform-*.yaml` y A deja `fleet-*.yaml`. Sync-waves: `-10` ESO · `-5` CA, KEDA, Traefik · `0` NATS, Redis · `5` Dapr · `8` componentes Dapr + Job de JetStream · `10` fake-llm, llm-gateway · `15` agentes.

## 9. Makefile → scripts (S escribe el Makefile, cada equipo su script)

| Target | Script | Dueño |
|---|---|---|
| `bootstrap` | `infra/scripts/bootstrap.sh` | P |
| `seed-secrets` | `infra/scripts/seed-secrets.sh` | P |
| `up` / `down` | `infra/scripts/lab.sh up\|down` | P |
| `tunnel` | `infra/scripts/tunnel.sh` | P |
| `cost-check` | `infra/scripts/cost-check.sh` | P |
| `local-up` / `local-down` | `scripts/local/k3d.sh up\|down` | P |
| `compose-up` / `compose-down` | `docker compose -f apps/docker-compose.yml ...` | A |
| `test` | `apps/scripts/test.sh` | A |
| `validate` | `infra/scripts/validate.sh` + `apps/scripts/validate.sh` | P + A |
| `demo N=<n>` | `scripts/demos/<NN>-*.sh` | P / A según §1 |

## 10. Arquitectura de código (obligatoria)

- **Apps (Python): Clean / Hexagonal.** Por servicio: `domain/` (Python puro), `application/` (casos de uso + puertos), `adapters/inbound/` (FastAPI, suscripciones y Workflow de Dapr), `adapters/outbound/` (OpenAI, Dapr pub/sub, NATS KV, telemetría) y `bootstrap/` (composition root con inyección de dependencias). Las dependencias solo apuntan hacia dentro; se verifica con **import-linter** en CI. Tests unitarios de dominio y aplicación con fakes, sin red.
- **Infra:** módulos Terraform de responsabilidad única con variables tipadas y validadas; scripts con `set -euo pipefail` que pasan `shellcheck`.
- **Calidad en CI:** ruff, tipado estricto, cobertura ≥ 80 %, import-linter, shellcheck, hadolint y Checkov.

## 11. Reglas para todos

- Sin `terraform apply`, sin crear recursos en AWS, GitHub, Grafana u OpenAI. Solo validación local.
- Sin `git commit` ni `git push`.
- Versiones fijadas (charts por versión, imágenes por digest cuando se conozca, acciones por SHA). Si una versión no se pudo verificar, se marca `# TODO(verify)` y se reporta.
- Nada de secretos en archivos. Ejemplos con valores ficticios en `*.example`.
- Lo que no se pudo validar se dice explícitamente en `docs/validation/<capa>.md`. No se inventan resultados.
