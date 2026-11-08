# Agentic Platform: plataforma cloud native para una flota de agentes IA

> **Estado:** en construcción. El diseño está cerrado ([plan](docs/IMPLEMENTATION_PLAN.md) y [ADRs](docs/adrs/)); la evidencia de lo que ya funciona está en [`docs/validation-log.md`](docs/validation-log.md). Lo que no aparece allí no se ha demostrado todavía.

> **Single control plane, sin HA.** El cluster tiene un único nodo de control plane (K3s con su datastore local). Si ese nodo se pierde, se pierde el cluster y se recrea desde Git y Terraform. Es una decisión consciente para un laboratorio efímero de costo mínimo, no un diseño de producción.

## Qué es

Un laboratorio **efímero y reproducible** que levanta, con un comando, una plataforma Kubernetes completa sobre **K3s autogestionado en EC2**. Encima corre una **flota de agentes que usan un LLM**: un orquestador, un investigador, un agente de análisis y un agente de ejecución, cada uno como microservicio independiente. El modelo decide el flujo de cada tarea.

La flota es la carga que pone a prueba la plataforma. Se comporta como cualquier trabajo distribuido (colas, reintentos, escalado, fallos parciales), con una particularidad: cada llamada al modelo real cuesta dinero. Por eso la arquitectura aguanta una prueba de carga o un ataque **sin gastar tokens reales**.

El entorno AWS solo existe durante los ensayos y la defensa (unas horas) y se destruye al terminar.

## Qué demuestra

- **Infraestructura como código:** Terraform (VPC, IAM, EC2, ASG, NLB) ejecutado desde GitHub Actions con OIDC, sin access keys.
- **GitOps:** Argo CD despliega todo desde Git (app-of-apps, sync-waves, `prune` y `selfHeal`). GitHub Actions nunca toca el cluster.
- **Elasticidad en dos niveles:** KEDA/HPA escala los agentes por profundidad de cola y CPU; Cluster Autoscaler añade y quita EC2 del ASG; el NLB registra y desregistra los nodos. Con techo explícito: nunca más de 3 EC2.
- **Mensajería y orquestación durable:** NATS JetStream con consumidores durables y Dapr Workflow, que reanuda una tarea desde el último paso si su pod muere.
- **Resiliencia:** backpressure (`429`/`503` con `Retry-After`), circuit breaker, idempotencia, DLQ y degradación a un LLM simulado.
- **Control de gasto del LLM:** tres barreras independientes (admisión con token, presupuesto global en el gateway y límite del proyecto en OpenAI).
- **Seguridad:** un rol IAM por controlador, IMDSv2, NetworkPolicy default-deny, imágenes distroless non-root, mTLS entre agentes, secretos solo en SSM.
- **Observabilidad:** métricas, logs y trazas en Grafana Cloud, organizadas por las 4 Golden Signals, más el consumo de tokens.
- **Portabilidad:** los mismos charts corren en `docker compose`, en k3d local y en EC2.

## Arquitectura

Internet → **NLB** (`:80`) → NodePort `30080` en los workers → **Traefik** (DaemonSet, rate limit) → **orquestador**. El orquestador ejecuta cada tarea como un **Dapr Workflow**: pide al modelo la siguiente acción a través de **`llm-gateway`** (el único servicio con la API key, que decide entre OpenAI y `fake-llm`) y delega en los demás agentes por **NATS JetStream**. El estado de los workflows vive en **Redis**. El **control plane** (t3.large) aloja K3s, AWS CCM, Cluster Autoscaler, KEDA, External Secrets, Argo CD, Dapr, NATS, Redis y `fake-llm`; un **ASG de workers** (t3.medium, 1 a 2) aloja los agentes y el gateway. Alloy envía la telemetría a Grafana Cloud.

Diagramas (C4, red, runtime agéntico, secuencia de una tarea, CI/CD y elasticidad): [`docs/IMPLEMENTATION_PLAN.md` §2](docs/IMPLEMENTATION_PLAN.md#2-arquitectura-objetivo). Índice: [`docs/architecture.md`](docs/architecture.md).

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `infra/` | Terraform (`bootstrap`, `modules`, `envs/lab`, plantillas de user-data) y scripts de operación |
| `kubernetes/` | Bootstrap de K3s (CCM, Argo CD) y el chart `agent-service` común a toda la flota |
| `gitops/` | Lo que Argo CD sincroniza: plataforma, overlays por cluster y apps |
| `apps/` | Agentes, `llm-gateway`, `fake-llm`, `docker-compose.yml` y pruebas k6 |
| `observability/` | Dashboards y Terraform de Grafana Cloud |
| `scripts/` | Perfil local (k3d) y scripts de demo con asserts |
| `docs/` | Plan, ADRs, contratos, versiones, runbook y evidencia |

## Prerrequisitos

| Herramienta | Uso |
|---|---|
| Git, Bash (Git Bash en Windows), GNU `make` | Todo el repo; los scripts son Bash |
| Docker | `compose`, k3d, k6 (`grafana/k6`) y hadolint |
| `kubectl`, Helm 4, k3d | Cluster local y acceso al cluster de AWS |
| Terraform | Capa persistente (`make bootstrap`) y respaldo local de `lab.yml` |
| AWS CLI v2 + `session-manager-plugin` | Credenciales, SSM y túnel al API server |
| `gh`, `jq`, `yq`, `uv` | Workflows de GitHub, scripts y apps Python |
| `pre-commit` | Hooks (`gitleaks`, `terraform fmt`, `ruff`, `hadolint`) |

Cuentas: AWS (región `us-east-1`), GitHub (repo público + GHCR), Grafana Cloud (free tier) y, solo para el modo `live`, un proyecto de OpenAI con límite de gasto de 5 USD. Versiones exactas en [`docs/versions.md`](docs/versions.md).

```bash
pipx install pre-commit && pre-commit install
make help
```

## Quickstart local (costo cero)

Todo el desarrollo usa `fake-llm` (`LLM_GLOBAL_MODE=simulated`): **cero tokens reales**.

```bash
# 1. Flota completa en docker compose (NATS, Redis, Dapr, gateway, fake-llm y agentes)
make compose-up
make test
make compose-down

# 2. Cluster k3d con Argo CD y los mismos charts que en AWS
make local-up
make demo N=1          # escenarios 1–6 y 10 funcionan en local
make local-down
```

## Quickstart en AWS

```bash
# Una sola vez: capa persistente (bucket S3 de estado, OIDC de GitHub, AWS Budget)
make bootstrap
make seed-secrets      # pide los secretos externos y los guarda en SSM (SecureString)

# Cada ensayo o defensa (requiere aprobación en el environment `lab`)
gh workflow run lab.yml -f action=up
make tunnel            # túnel SSM al API server y kubeconfig en local
make demo N=7

# Al terminar
gh workflow run lab.yml -f action=down   # terraform destroy + cost-check
```

`make up` / `make down` hacen lo mismo desde la laptop como respaldo si GitHub Actions no está disponible.

## Escenarios de demo

Cada escenario tiene un script en [`scripts/demos/`](scripts/demos/) que lo ejecuta y comprueba el resultado con asserts: `make demo N=<n>`.

| # | Escenario | Script | Evidencia automática | Local |
|---|---|---|---|---|
| 1 | Despliegue normal | `01-deploy.sh` | Apps `Synced/Healthy`, `curl` 200 vía NLB | Sí |
| 2 | Sync GitOps | `02-gitops-sync.sh` | Commit → nueva revisión en Argo → nuevo SHA en el pod | Sí |
| 3 | Self-healing | `03-self-heal.sh` | `kubectl delete pod` → réplica restaurada; drift manual revertido | Sí |
| 4 | Aumento de tráfico | `04-traffic.sh` | k6 ramp, RPS y p95 | Sí |
| 5 | HPA | `05-hpa.sh` | El HPA sube a más de 1 réplica | Sí |
| 6 | Pending | `06-pending.sh` | Eventos `FailedScheduling: Insufficient cpu` | Sí |
| 7 | Cluster Autoscaler lanza EC2 | `07-ca-scaleup.sh` | Evento `TriggeredScaleUp` + `DesiredCapacity=2` | No |
| 8 | Join de K3s | `08-node-join.sh` | Nuevo nodo `Ready` con `providerID` válido | No |
| 9 | Registro en el NLB | `09-nlb-target.sh` | `describe-target-health` = healthy | No |
| 10 | Distribución | `10-distribution.sh` | Conteo por `X-Pod-Name` y métricas por pod | Sí |
| 11 | Scale-down | `11-scale-down.sh` | KEDA al mínimo o a cero, `ScaleDown`, instancia terminada, Node y target eliminados | No |
| 12 | Grafana | `12-grafana.sh` | La API de Grafana Cloud devuelve series recientes | No |
| 13 | Ataque / abuso | `13-attack.sh` | `429` en el borde, `tasks_shed_total` > 0, ASG ≤ 2, **0 tokens `live`** | Sí |
| 14 | Caos del LLM | `14-chaos.sh` | Circuito abierto, DLQ/reintentos, ningún `task_id` perdido | Sí |
| 15 | Demo `live` y degradación | `15-live.sh` | Tokens `live` > 0 con token de demo; presupuesto agotado → `degraded=true` | No |

## Costos y cómo destruir

Precios on-demand de `us-east-1` (a verificar antes de la defensa). Detalle en el [plan §9](docs/IMPLEMENTATION_PLAN.md#9-costos-precios-on-demand-de-us-east-1-verificar-antes-de-la-defensa).

| Concepto | Estimación |
|---|---|
| Lab encendido (1 t3.large + 1–2 t3.medium + NLB + IPv4 + EBS) | **~0.19–0.23 USD/h** |
| Ensayo o defensa (~3 h) | ~0.7 USD cada uno |
| Capa persistente (S3, SSM, Budget) | < 0.05 USD/mes |
| GitHub Actions, GHCR y Grafana Cloud (free) | 0 |
| LLM en desarrollo, CI, carga, ataque y caos (`fake-llm`) | **0** |
| LLM `live` (test de contrato + demo) | ≤ 5 USD (límite del proyecto OpenAI; el gateway corta en 3 USD) |
| **Total del proyecto** (2 ensayos + defensa) | **≈ 3–5 USD** |

**Destruir:**

```bash
gh workflow run lab.yml -f action=down   # o: make down
make cost-check                          # falla si queda cualquier recurso del proyecto
```

Salvaguardas: AWS Budget de 10 USD con alertas, `cost-check` tras cada `down` y `lab-reaper.yml`, que destruye el lab si lleva encendido más de `LAB_TTL_HOURS` (6 h). Nada de lo que corre en el cluster crea recursos AWS (sin EBS CSI, sin service controller del CCM, sin NAT ni EIP). La capa persistente no se destruye con el lab; para eliminarla, `terraform destroy` en `infra/terraform/bootstrap`.

## Desviaciones del brief

Decisiones conscientes, justificadas en los ADRs:

| Brief | Este proyecto | Por qué | Detalle |
|---|---|---|---|
| ingress-nginx | **Traefik** (chart oficial, recurso estándar `Ingress`) | ingress-nginx está retirado y sin parches de seguridad desde marzo de 2026 | [ADR-0001 §4](docs/adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md#4-tecnología-elegida-y-desviaciones-del-brief) |
| Docker Hub | **GHCR** para las apps y un mirror por digest de las imágenes de plataforma; tarball airgap para K3s | Los límites de pull anónimo de Docker Hub podrían bloquear el scale-up en plena demo | [ADR-0001 §4](docs/adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md#4-tecnología-elegida-y-desviaciones-del-brief) |
| Sin KEDA en el camino crítico | **KEDA** (cola de JetStream + CPU), con escalado a cero | Un agente LLM espera I/O: su CPU no refleja la carga, la cola sí | [ADR-0002 §5](docs/adrs/0002-identidad-credenciales-y-elasticidad.md#5-elasticidad-acotada) |
| Evitar componentes innecesarios | **Dapr** (Workflow, pub/sub, mTLS) + Redis | Orquestación durable, trazado automático y mTLS entre agentes | [ADR-0001 §3](docs/adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md#3-flota-agéntica) |
| Sin APIs de LLM externas | **API de OpenAI** solo en modo `live` protegido; `fake-llm` para todo lo demás | Demostrar un LLM real con gasto acotado por tres barreras | [ADR-0002 §6](docs/adrs/0002-identidad-credenciales-y-elasticidad.md#6-resiliencia-ante-carga-y-ataque-y-contención-del-gasto-llm) |
| CD desde GitHub Actions | **CD por Argo CD** (GitOps); Actions solo promueve el tag en Git | GitOps puro, sin SSH ni API server expuestos | [ADR-0001 §2](docs/adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md#2-github-como-plano-de-orquestación-y-orden-de-arranque) |

## Limitaciones conocidas

- **Single control plane, sin HA** (ver arriba). El plano de control de Dapr, NATS y Redis también corren con 1 réplica.
- Sin TLS en el NLB porque no hay dominio. Con dominio: listener TLS + ACM, sin costo de certificado.
- Las pruebas de carga usan `fake-llm`: validan la plataforma, no la calidad del modelo.
- Los paquetes de GHCR se crean privados y se hacen públicos a mano una vez.

## Documentación

- [Plan de implementación](docs/IMPLEMENTATION_PLAN.md) · [Arquitectura](docs/architecture.md) · [Contratos entre capas](docs/CONTRACTS.md)
- [ADR-0001: plataforma, flota agéntica y ciclo de vida efímero](docs/adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md)
- [ADR-0002: identidad, credenciales, elasticidad y resiliencia](docs/adrs/0002-identidad-credenciales-y-elasticidad.md)
- [Versiones](docs/versions.md) · [Runbook](docs/runbook.md) · [Registro de validación](docs/validation-log.md) · [Scripts de demo](scripts/demos/README.md)

Repositorio: <https://github.com/Andresm98/03-agentic-platform-swe>

## Licencia

[MIT](LICENSE) © Andresm98
