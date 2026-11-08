# Arquitectura: índice

Este documento es un índice. Los diagramas viven en un solo sitio, la [§2 del plan de implementación](IMPLEMENTATION_PLAN.md#2-arquitectura-objetivo), para que no haya dos versiones que se desincronicen. Las decisiones y su porqué están en los ADRs.

## Diagramas (Mermaid)

| Vista | Qué muestra | Enlace |
|---|---|---|
| C4 nivel 1: contexto | Operador, público/k6 y servicios externos (GitHub, AWS, OpenAI, Grafana Cloud) | [§2.A](IMPLEMENTATION_PLAN.md#2a-modelo-c4) |
| C4 nivel 2: contenedores | Traefik, agentes, `llm-gateway`, `fake-llm`, NATS JetStream, Redis y plano de plataforma | [§2.A](IMPLEMENTATION_PLAN.md#2a-modelo-c4) |
| C4 nivel 3: componentes del orquestador | API HTTP, Dapr Workflow, actividades decidir/delegar, telemetría | [§2.A](IMPLEMENTATION_PLAN.md#2a-modelo-c4) |
| Infraestructura, red y ubicación de pods | VPC, NLB, control plane, ASG de workers, capa persistente, qué corre en cada nodo | [§2.B](IMPLEMENTATION_PLAN.md#2b-plataforma-infraestructura-red-y-ubicación-de-pods) |
| Runtime agéntico | Pods con sidecar `daprd`, pub/sub sobre JetStream, KV de presupuesto, control del LLM | [§2.C](IMPLEMENTATION_PLAN.md#2c-plataforma-agéntica-runtime-mensajería-y-control-del-llm) |
| Secuencia de una tarea | `POST /tasks` → bucle decidir/delegar → `tasks.completed` | [§2.D](IMPLEMENTATION_PLAN.md#2d-secuencia-de-una-tarea) |
| CI/CD y GitOps | `main.yml` por etapas → GHCR → promoción en `gitops/` → Argo CD → `post-deploy.yml` | [§2.E](IMPLEMENTATION_PLAN.md#2e-cicd-y-gitops-flujos-de-ida-y-vuelta) |
| Cadena de elasticidad | KEDA/HPA → Pending → Cluster Autoscaler → EC2 → NLB, y la bajada | [§2.F](IMPLEMENTATION_PLAN.md#2f-cadena-de-elasticidad-subida-y-bajada) |
| Reglas de Security Groups | Puertos permitidos entre NLB, workers y control plane | [§2.1](IMPLEMENTATION_PLAN.md#21-reglas-de-security-groups) |
| Presupuesto de capacidad | Requests por pod y cuántos agentes de ejecución caben por worker | [§2.2](IMPLEMENTATION_PLAN.md#22-presupuesto-de-capacidad-para-la-demo-de-pending-y-del-ca) |

GitHub renderiza Mermaid directamente. En VS Code hace falta una extensión de vista previa de Mermaid. Los diagramas C4 usan la sintaxis experimental de Mermaid; si alguno no se renderiza, §2.B y §2.C tienen la misma información como flowchart.

## Decisiones (ADRs)

| ADR | Tema |
|---|---|
| [ADR-0001](adrs/0001-plataforma-bootstrap-y-ciclo-de-vida.md) | Dueños de cada capa (L-1 persistente, L0 infra, L1 bootstrap, L2 GitOps), GitHub como plano de orquestación, flota agéntica con Dapr, desviaciones del brief, costo y destrucción garantizada, día de la defensa |
| [ADR-0002](adrs/0002-identidad-credenciales-y-elasticidad.md) | Identidad del nodo (IMDSv2, `providerID`), un rol IAM por controlador sin IRSA, OIDC de GitHub, aislamiento, exposición pública, elasticidad acotada y las tres barreras de gasto del LLM |

## Contratos y versiones

- [CONTRACTS.md](CONTRACTS.md): nombres, rutas, namespaces, endpoints internos, parámetros SSM, subjects de NATS y sync-waves compartidos entre capas.
- [versions.md](versions.md): versiones fijadas y su estado de verificación.

## Operación y evidencia

- [runbook.md](runbook.md): troubleshooting por fase.
- [validation-log.md](validation-log.md): evidencia real por fase.
