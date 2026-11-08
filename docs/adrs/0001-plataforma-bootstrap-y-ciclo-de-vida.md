# ADR-0001: Plataforma, flota agéntica y ciclo de vida efímero

- **Estado:** Aceptado
- **Fecha:** 2026-11-07
- **Relacionado:** [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) · [ADR-0002](0002-identidad-credenciales-y-elasticidad.md)

## Contexto

El laboratorio demuestra una **plataforma cloud native completa** sobre K3s autogestionado en EC2. Cubre infraestructura como código, orquestación, GitOps, red y balanceo, elasticidad de pods y nodos, mensajería, observabilidad y seguridad. La carga de trabajo es una **flota de agentes que usan un LLM**: el modelo decide el flujo y cada agente es un microservicio independiente.

La flota es la carga que pone a prueba la plataforma, no su sustituto. Una tarea de un agente se comporta como cualquier otro trabajo distribuido (cola, reintentos, escalado, fallos parciales), con una particularidad que define este laboratorio: **cada llamada al modelo real cuesta dinero**. La arquitectura debe soportar una prueba de carga o un ataque sin gastar tokens reales (ADR-0002).

Condiciones de operación:
- **Demo pública y efímera.** Solo existe durante los ensayos y la defensa (unas horas) y después se ejecuta `terraform destroy`.
- **Principios CNCF:** replicabilidad, elasticidad y portabilidad, con costo mínimo.

Problemas que resuelve este ADR:
1. **CCM.** Con `cloud-provider=external`, los nodos nacen con el taint `uninitialized`. El CCM tiene que llegar antes que Argo CD.
2. **Argo CD tardío.** El brief lo instala en la fase G, y adoptar después releases de Helm instaladas a mano duplica trabajo.
3. **Varios dueños.** Terraform, K3s, Argo CD, Cluster Autoscaler y KEDA pueden modificar el mismo estado.
4. **Costo.** Puede haber recursos AWS huérfanos tras el `destroy` y gasto de tokens del LLM.

## Decisión

### 1. Cada recurso tiene un único dueño

| Capa | Dueño | Contenido | Ciclo de vida |
|---|---|---|---|
| **L-1: Persistente** | `infra/terraform/bootstrap` (se aplica una vez desde local) + `seed-secrets.sh`; `observability/terraform` (aplicado por `observability.yml`) | Bucket S3 de estado (cifrado, `use_lockfile`), AWS Budget de 10 USD con alertas, **proveedor OIDC de GitHub + rol `agentic-github-actions`**, parámetros SSM de secretos externos (token de Grafana Cloud, API key de OpenAI, token de demo, credenciales de la GitHub App de Argo CD), paquetes públicos en GHCR, dashboards y datasource CloudWatch en Grafana Cloud | Se crea una vez; < 0.05 USD/mes |
| **L0: Infra AWS** | `infra/terraform/envs/lab`, ejecutado por **GitHub Actions** (`lab.yml`) | VPC, SGs, IAM, EC2 del control plane, launch template, ASG, NLB y target group, rol CloudWatch para Grafana, parámetro del join token | `lab.yml up` / `lab.yml down` (`make up/down` como respaldo local) |
| **L1: Bootstrap** | user-data + helm-controller de K3s | K3s, **AWS CCM** (`HelmChart` con `bootstrap: true`), **Argo CD** + `root-app` | Inmutable; un cambio implica recrear el lab |
| **L2: Estado deseado** | Argo CD (`gitops/`) | Cluster Autoscaler, KEDA, Traefik, External Secrets, NATS, **Dapr (plano de control, componentes y Dashboard) + Redis del estado de workflows**, k8s-monitoring/Alloy, **ApplicationSet de la flota agéntica**, `llm-gateway`, `fake-llm`, ScaledObjects, PDB, NetworkPolicies, notificaciones de Argo CD | Commit en Git |

Recursos compartidos:
- **`desired_capacity` del ASG:** su dueño en ejecución es el CA; Terraform lo ignora.
- **Réplicas de los agentes:** su dueño es KEDA (HPA generado). Los manifiestos no fijan `replicas`.
- **Join token:** lo escribe el control plane; Terraform ignora su valor.
- **Control plane:** `ignore_changes = [ami, user_data]`.
- **`image.tag`:** solo lo escribe CI; CI nunca toca el cluster.
- **PVC de NATS y de Redis:** `Prune=false`.

### 2. GitHub como plano de orquestación y orden de arranque

El repositorio orquesta la arquitectura completa. Hay **dos direcciones de flujo** y una regla que no se rompe: **GitHub Actions nunca aplica nada al cluster de Kubernetes**; el cluster solo cambia porque Argo CD lee Git.

**Modelo de pipeline:** se toma como referencia el patrón de [`Andresm98/devops-platform-challenge`](https://github.com/Andresm98/devops-platform-challenge/tree/dea4ec224cb0562231a35624cf14144bf030d140/.github): un **orquestador principal** que encadena **workflows reutilizables** (`workflow_call`) por etapas con `needs`, y el despliegue condicionado a `main`.

```
main.yml (push/PR a main·dev, paths-ignore docs/**, workflow_dispatch)
 ├─ Stage 1 — CI ............ _ci.yml          ruff, pytest + cobertura ≥ 80 %, SonarCloud    (matriz por servicio)
 │                            _iac-scan.yml    terraform fmt/validate, tflint, Checkov, helm lint, kubeconform, gitleaks
 ├─ Stage 2 — Imágenes ...... _images.yml      build distroless → Trivy (CRITICAL) → push a GHCR :<sha> + SBOM y provenance
 │                                             (push solo en main; en PR, build y scan sin push)
 └─ Stage 3 — Promoción GitOps _gitops-promote.yml  yq image.tag=<sha> en gitops/ + commit  (solo push a main)
                                                    → Argo CD despliega (la "CD" ya no es de Actions)
```

Qué se adopta de la referencia y qué se corrige para cumplir este ADR y el ADR-0002:

| Referencia | En esta plataforma | Motivo |
|---|---|---|
| Orquestador + `workflow_call` por etapas, `needs`, `if:` por rama | **Se adopta** | Etapas legibles en la UI de Actions y reutilizables |
| Cobertura con umbral, SonarCloud, Checkov, Trivy antes del push | **Se adopta** (Checkov sin `soft_fail` una vez estabilizado) | Calidad y seguridad *shift-left* |
| Acciones en `@master` / `@vN` | Fijadas por **commit SHA** + Dependabot | Una etiqueta móvil ejecuta código que no se revisó |
| `secrets: inherit` | Secretos **explícitos** por workflow reutilizable y `permissions:` mínimos por job | Cada etapa ve solo lo que necesita |
| Tag `:latest` | Solo `:<git-sha>` (y digest) | Inmutabilidad |
| Build para escanear y segundo build para publicar | **Un solo build**: se publica exactamente la imagen escaneada | Lo publicado es lo verificado |
| Push también en PR | Push solo en `main` | Un PR no publica imágenes |
| `AWS_ACCESS_KEY_ID`/`SECRET` en secrets | **OIDC** + environment con aprobación | Sin credenciales de larga duración en un repo público |
| SSH con clave privada + `kubectl apply` + `sed` de la imagen | **Argo CD** lee Git; Actions solo promueve el tag | GitOps; sin puerto 22 ni API server expuestos |
| `terraform apply -auto-approve` en cada push a `main` | `lab.yml` **manual**, con `plan` visible y aprobación | El lab es efímero y cuesta dinero |
| Manifiestos de terceros por URL sin fijar (Kong) | Charts fijados por versión en `gitops/platform` | Reproducibilidad |

Workflows independientes del orquestador principal:

| Workflow | Disparador | Qué orquesta | Credenciales |
|---|---|---|---|
| `main.yml` (+ `_ci`, `_iac-scan`, `_images`, `_gitops-promote`) | push / PR / manual | Ver el esquema anterior | `GITHUB_TOKEN` (`contents: write` solo en la promoción, `packages: write` solo en imágenes); `SONAR_TOKEN` solo para `_ci` |
| `mirror-images.yml` | cambio en `platform-images.lock` / manual | Copia por digest de imágenes de plataforma a GHCR | `GITHUB_TOKEN` |
| `lab.yml` | **manual** (`action: up\|down`) | `terraform apply`/`destroy` de `envs/lab` + `cost-check.sh` | OIDC → `role/agentic-github-actions`, environment `lab` con **aprobación tuya** |
| `lab-reaper.yml` | cron cada hora | Destruye el lab si su tag `CreatedAt` supera `LAB_TTL_HOURS` (6 h por defecto) | Igual que `lab.yml` |
| `observability.yml` | cambio en `observability/` / manual | Dashboards y datasource de Grafana Cloud (Terraform, provider `grafana`) | Token de Grafana en el environment `observability` |
| `post-deploy.yml` | **`deployment_status` creado por Argo CD** | Smoke tests de caja negra contra el NLB (escenario 1) y estado del commit | `GITHUB_TOKEN` |

**Flujo de ida (GitHub → AWS / GHCR / Grafana / Git):** Actions provisiona AWS, publica imágenes, configura Grafana y escribe en `gitops/`.

**Flujo de vuelta (Argo CD → GitHub Actions):**
1. Al sincronizar una Application y quedar `Healthy`, el servicio GitHub de **Argo CD Notifications** crea un *GitHub Deployment* (environment `aws-lab`, con la revisión) y su estado.
2. Ese evento `deployment_status` dispara `post-deploy.yml`.
3. `post-deploy.yml` verifica desde fuera y marca el commit.
4. Si la sincronización falla o la Application queda `Degraded`, el estado del Deployment es `failure` y aparece en el commit.

Así, cada commit muestra en GitHub si llegó al cluster y si funciona, sin que Actions toque Kubernetes.

**Flotas como despliegue declarativo:** un **ApplicationSet** genera una Application por directorio de `gitops/apps/agents/*`. Añadir un agente a la flota es añadir un directorio con sus values, y Argo CD lo despliega solo. La UI de Argo CD muestra la flota y el estado de cada agente. Es la orquestación de **despliegue**. La orquestación de la **ejecución** es un workflow durable de Dapr dirigido por el modelo (§3).

Orden de arranque:

```
gh workflow run lab.yml -f action=up → (aprobación) → terraform apply → CP: K3s server (+ imágenes airgap) → token a SSM → CCM → Argo CD + root-app
               → ASG: worker espera el token → K3s agent
Argo CD sync-waves: external-secrets → cluster-autoscaler, keda, traefik → nats, redis → dapr (control plane) → componentes Dapr + consumidores JetStream → fake-llm, llm-gateway → agentes
```

Argo CD se instala en la **fase C**. Política de sync: `prune: true` y `selfHeal: true` en L2. Cualquier cambio se hace con un commit.

### 3. Flota agéntica

| Agente | Rol (el modelo decide) | Herramientas | Escalado (ADR-0002) |
|---|---|---|---|
| **Orquestador** | Cada tarea es una **instancia de Dapr Workflow**. En cada paso, una actividad consulta al modelo, que decide la siguiente acción (*tool call*); el workflow la ejecuta como actividad (delegar a otro agente y esperar su evento de respuesta) y repite hasta `finish` o el límite de pasos | `dispatch_research`, `dispatch_analysis`, `dispatch_execution`, `finish` | KEDA por cola de entrada |
| **Investigador** | Recopila contexto | Base de conocimiento local versionada en la imagen; **sin búsqueda web** (coste cero, decidido) | KEDA por cola, **escala a cero** |
| **Análisis** | Evalúa y razona sobre resultados (sustituye al *evaluator* del brief y publica `task.evaluated`) | Reglas y puntuación deterministas | KEDA por cola, escala a cero |
| **Ejecución** | Ejecuta acciones con herramientas deterministas que consumen **CPU real** (sustituye al *executor* del brief) | Funciones Python de una lista cerrada; sin shell | KEDA: **CPU 60 % + cola**, mínimo 1 y máximo 8 |

Contrato común:
- **Runtime: Dapr** (sidecar `daprd` en cada pod de la flota). Los agentes hablan con su sidecar por localhost y no conocen el broker ni el almacén:
  - **Pub/sub:** componente `pubsub.jetstream` sobre el **mismo NATS JetStream** (`tasks.*`, `agent.<rol>.requested|completed`, correlación por `task_id`). NATS sigue siendo el broker y la fuente de `num_pending` para KEDA. Los consumidores durables se crean por adelantado (Job en sync-wave) para que KEDA pueda escalar desde cero.
  - **Workflow:** el orquestador usa **Dapr Workflow**. Cada paso completado queda persistido; si el pod muere a mitad de una tarea, otra réplica la **reanuda desde el último paso persistido**: las llamadas al modelo ya completadas no se repiten, y la que estaba en curso al caer el pod sí (entrega al menos una vez).
  - **Estado:** el estado de los workflows necesita un almacén con transacciones (actor state store): **Redis**, 1 réplica en el control plane con PV y `Prune=false`. El presupuesto del LLM sigue en NATS KV (ADR-0002 §6).
  - **Seguridad:** mTLS entre sidecars (Sentry) y control de acceso por `app-id` a nivel de componente (cada agente solo publica y se suscribe en sus topics).
  - **Visualización del flujo:** Dapr genera **automáticamente** spans de pub/sub, invocación y actividades de workflow, y los envía por OTLP a Alloy → Grafana Cloud Traces. Las apps añaden spans propios (decisión del modelo, herramienta, tokens). **Dapr Dashboard** (port-forward) muestra las apps de la flota, sus componentes y su configuración, y el historial de cada instancia de workflow se consulta por su API.
  - **Agentes sin estado:** todo el estado vive en Dapr Workflow y Redis, así que los agentes se pueden escalar y matar libremente.
  - **Madurez:** se usa el SDK de Dapr Workflow para Python con el bucle de agente propio, para que el modelo siga decidiendo y el control de gasto siga en el gateway. El framework Dapr Agents se evalúa en la Fase 0 (madurez y versión) antes de adoptarlo.
- **Acceso al modelo:** siempre vía **`llm-gateway`**, un endpoint interno compatible con la API de OpenAI. Ningún agente tiene la API key ni salida a Internet. El gateway decide si una llamada va a OpenAI o a `fake-llm` (ADR-0002 §6).
- **Portabilidad:** los agentes usan el SDK oficial de OpenAI con `base_url` apuntando al gateway. Cambiar de proveedor (otro servicio compatible, un modelo local futuro) es un cambio de configuración, no de código.
- **Imágenes:** build multistage → **distroless** `gcr.io/distroless/python3-debian12:nonroot` (fijada por digest). El builder usa la **misma versión menor de Python** que la imagen distroless. Sin shell ni gestor de paquetes, non-root, `readOnlyRootFilesystem`.
- **Modelo por agente:** cada agente define `LLM_MODEL` y su `max_tokens` en sus values. El gateway solo admite los modelos de su lista permitida, con su precio por token configurado, para convertir el consumo en USD. Con 5 USD de límite total, se eligen modelos pequeños y económicos y peticiones muy modestas (ADR-0002 §6).
- **Trazabilidad de los flujos agénticos:** una tarea es **una traza**: orquestador → actividades del workflow → delegaciones por pub/sub → herramientas → llamadas al modelo, con modo, modelo y tokens como atributos. Dapr propaga el contexto W3C (`traceparent`) entre sidecars; las apps lo propagan hacia el gateway. Se ve en **Grafana Cloud Traces (Tempo)** como cascada y como grafo de servicios. El dashboard de agentes enlaza cada `task_id` con su traza.

**Arquitectura de código (obligatoria en todo el proyecto):**
- **Clean / Hexagonal por servicio:**
  - `domain/`: Python puro, sin frameworks.
  - `application/`: casos de uso y **puertos** (`LLMPort`, `EventPublisherPort`, `BudgetStorePort`, `TaskStatePort`, `TelemetryPort`…).
  - `adapters/inbound/`: FastAPI, suscripciones y Workflow de Dapr.
  - `adapters/outbound/`: OpenAI vía gateway, Dapr pub/sub, NATS KV, OTel/Prometheus, LangSmith.
  - `bootstrap/`: composition root con inyección de dependencias.
- **Dependencias solo hacia dentro.** Dapr, OpenAI y NATS son detalles intercambiables detrás de puertos; cambiarlos no toca el dominio. **import-linter** lo verifica en CI.
- **Tests:** unitarios de dominio y aplicación con fakes en memoria; tests de adapters por separado.
- **Calidad en CI:** ruff, tipado estricto, cobertura ≥ 80 %, shellcheck, hadolint, Checkov.
- **Infra:** módulos Terraform de responsabilidad única y scripts con funciones pequeñas.

**Frameworks de LLM:**
- **LangChain y LangGraph: no.** LangGraph es otro motor de orquestación con su propio estado (checkpointers) y competiría con Dapr Workflow: habría dos fuentes de verdad sobre en qué paso está cada tarea. LangChain añade una abstracción pesada sobre el SDK de OpenAI que ya cumple el papel de puerto, aumenta el tamaño de las imágenes distroless y cambia de API con frecuencia.
- **LangSmith: sí, activado por defecto (obligatorio).**
  - **Dónde:** solo en `llm-gateway`, que es el único punto de salida y el único que tiene secretos.
  - **Cómo:** detrás de `LLMTelemetryPort`, preferiblemente vía OTLP si LangSmith lo admite (`TODO(verify)` en la Fase 0); si no, con su SDK confinado al adaptador.
  - **Muestreo:** llamadas `live` al 100 %; simuladas a `LANGSMITH_SIMULATED_SAMPLE_RATE` (por defecto 1 %), para que las pruebas de carga y de ataque no agoten la cuota gratuita.
  - **Fail-open:** la exportación es asíncrona. Si LangSmith falla o va lento, la llamada al modelo continúa; solo sube `llm_telemetry_export_errors_total`, sin afectar a readiness.
  - **Qué aporta:** vista de prompts, respuestas, tokens y latencia por llamada al modelo. Complementa a Tempo, que muestra el flujo entre servicios.
  - **Secreto obligatorio:** `/agentic-platform/k8s/langsmith-api-key`.

**Ejercicios de estudiantes (rama `stage`):**
- **Modelo:** `main` y `develop` contienen la arquitectura; `stage` solo aporta `exercises/<nombre>/` y `gitops/stage/`. `stage` es un entorno lógico en el mismo cluster, porque un cluster aparte rompería el límite de 3 EC2.
- **Flujo:** PR a `stage` → CI sin secretos (reglas, build, Trivy y despliegue de prueba en un kind efímero dentro del runner) → revisión del instructor → publicación en GHCR → `gitops/stage/<nombre>/values.yaml` generado por CI → Argo CD → `/s/<nombre>/`.
- **Separación:** el estudiante solo controla `exercise.yaml` (`owner`, `port`, `description`). Los values, recursos y red los genera CI.
- **Controles:** revisión humana; un PR solo puede tocar su carpeta; máximo 3 ejercicios, comprobado en CI y con `ResourceQuota`; Pod Security `restricted`; NetworkPolicy sin salida salvo DNS; `AppProject` limitado al namespace `stage`; `ValidatingAdmissionPolicy` que solo admite imágenes del workflow por SHA.
- **Una sola imagen en GHCR** (`exercises:<nombre>-<sha>`): los paquetes nacen privados y solo se pueden hacer públicos a mano, así que una por estudiante rompería el flujo.
- **`kind-smoke.sh` usa `kubectl apply`** contra un cluster efímero del runner. La regla de que CI no aplica nada se refiere al cluster del laboratorio.

### 4. Tecnología elegida y desviaciones del brief

| Tema | Decisión | ¿Desviación del brief? |
|---|---|---|
| Ingress | **Traefik**, recurso estándar `Ingress` | Sí: ingress-nginx está retirado |
| Registry | **GHCR** (apps + mirror por digest de las imágenes de plataforma) y tarball airgap de K3s | Sí: Docker Hub tiene límites de pull que pondrían en riesgo el scale-up |
| Escalado de agentes | **KEDA** (escalador NATS JetStream + CPU) | Sí: el brief excluía KEDA del camino crítico. Un agente LLM espera I/O y su CPU no refleja la carga; la señal correcta es la cola (ADR-0002 §5) |
| LLM | **API de OpenAI** solo en modo `live` protegido; **`fake-llm`** compatible para carga, ataque y CI | Sí: el brief prohibía APIs de LLM externas. Se acota con el gateway y los presupuestos de ADR-0002 §6 |
| Secretos | External Secrets Operator + SSM Parameter Store | No |
| Repo | Público, con `gitleaks` | No |
| Runtime de la flota | **Dapr** (sidecars, Workflow, pub/sub sobre JetStream, mTLS, Dashboard) + Redis para el estado de workflows | Sí: el brief pide evitar componentes innecesarios. Se justifica por orquestación durable, trazado automático y mTLS entre agentes; el coste en recursos se mide y se acota (ADR-0002 §5) |
| Mensajería | NATS JetStream, 1 réplica, consumidores durables; KV para el presupuesto del LLM | No |
| Observabilidad | Alloy → Grafana Cloud free; CloudWatch a demanda; 4 Golden Signals + panel de tokens | No |
| Operación AWS | Terraform ejecutado por GitHub Actions con OIDC (sin access keys); AWS MCP descartado | No |
| Retroalimentación del despliegue | Argo CD Notifications → GitHub Deployments → `post-deploy.yml` | No |
| Visualización de flujos | Trazas Dapr + OpenTelemetry → Grafana Cloud Traces; Dapr Dashboard para la flota en ejecución; UI de Argo CD para la flota desplegada | No |
| CI/CD en GitHub | Orquestador + workflows reutilizables por etapas (modelo de referencia corregido, §2) | Sí: el brief pedía Docker Hub y CD de Actions; aquí GHCR y CD por Argo CD |

### 5. Costo y destrucción garantizada

- **Nada de lo que corre en el cluster crea recursos AWS:**
  - el service controller del CCM está desactivado;
  - no hay EBS CSI;
  - no se usan CloudWatch Logs ni Container Insights;
  - no hay NAT ni EIP.
- **`lab.yml down`** (o `make down`) = `terraform destroy` + `cost-check.sh`. La comprobación falla si quedan instancias, LBs, TGs, volúmenes, EIPs, ENIs o la VPC del proyecto.
- **Red de seguridad contra olvidos:** `lab-reaper.yml` destruye el lab si lleva encendido más de `LAB_TTL_HOURS` (6 h por defecto; se amplía con una variable del repo si una defensa se alarga).
- **Infraestructura:**
  - **Precio:** ~0.2 USD/h encendido; **3–5 USD** en todo el proyecto.
  - **Sin servicios de pago:** on-demand sin Spot, gp3 de 20 GB, sin detailed monitoring ni KMS CMK.
  - **Tags:** `default_tags` en todos los recursos.
- **LLM:**
  - **Por defecto, cero gasto:** `fake-llm` cubre local, CI y pruebas de carga o ataque.
  - **Gasto real acotado por tres topes** (ADR-0002 §6): el presupuesto global del gateway (3 USD), el límite por tarea y el límite de gasto del proyecto en OpenAI (**5 USD, decidido**).
- **Local primero:** k3d con los mismos charts para los escenarios 1–6, 10 y las pruebas de resiliencia. AWS solo se enciende para el CA, el join de nodos, el NLB, el scale-down y CloudWatch.

### 6. Día de la defensa

| Momento | Acción |
|---|---|
| T-60 | `gh workflow run lab.yml -f action=up` y aprobar (imágenes y mirrors ya en GHCR) |
| T-40 | Applications `Synced/Healthy` en la UI de Argo CD; `post-deploy.yml` en verde en GitHub |
| T-30 | `curl` público al NLB; una tarea `live` de humo; presupuesto LLM visible en Grafana |
| T-0 | Escenarios 1→14 con scripts que validan cada resultado |
| Fin | `gh workflow run lab.yml -f action=down` con `cost-check` en verde; Cost Explorer y consumo de OpenAI a las 24 h. Si se olvida, `lab-reaper` lo destruye. |

Los tiempos son estimados y se miden en el ensayo.

### 7. Principios CNCF

| Principio | Cómo se cumple |
|---|---|
| Replicabilidad | Terraform + GitOps. Versiones fijadas (K3s, charts, imágenes por SHA o digest, actions por SHA). Bootstrap idempotente. `make down && make up` reproduce el entorno. `fake-llm` determinista reproduce las pruebas. |
| Elasticidad | KEDA/HPA → Cluster Autoscaler → ASG → target group del NLB, en ambos sentidos, con techo explícito (ADR-0002). |
| Portabilidad | OCI distroless + Helm + APIs estándar (`Ingress`, HPA, PDB, NetworkPolicy). API de LLM compatible con OpenAI tras el gateway. Lo específico de AWS queda en L0 y en CCM, CA y ESO. El mismo código corre en compose, k3d y EC2. |
| Resiliencia | Workflows durables que se reanudan tras la caída de un pod, backpressure, bulkheads, circuit breaker, idempotencia, degradación a `fake-llm` (ADR-0002 §6). |
| Observabilidad | Prometheus, logs JSON con `task_id`, Alloy compatible con OpenTelemetry, métricas de tokens por agente y por modo. |

## Alternativas descartadas

- **Argo CD en la fase G:** obliga a adoptar releases de Helm más tarde.
- **CCM vía Argo CD:** imposible por el taint `uninitialized`.
- **Terraform con providers `helm`/`kubernetes`:** crea dos dueños para los mismos objetos.
- **ingress-nginx:** sin parches de seguridad.
- **Docker Hub:** límites de pull en pleno scale-up.
- **HPA por CPU para todos los agentes:** no ve la carga de un agente que espera I/O.
- **`prometheus-adapter` en lugar de KEDA:** más configuración y no escala a cero.
- **LLM local en el cluster:** t3 sin GPU; se comería el worker y falsearía la medición.
- **Agentes con la API key y llamando directamente a OpenAI:** sin punto único de control de gasto ni de degradación.
- **Proxy LLM de terceros con base de datos para presupuestos:** añade un componente con estado. El gateway propio usa NATS KV, que ya existe.
- **Agentes con shell o ejecución de código arbitrario en el cluster:** superficie de ataque inaceptable.
- **LangGraph como orquestador de agentes:** duplica a Dapr Workflow (dos motores de estado). **LangChain:** abstracción pesada sobre un SDK que ya está detrás de un puerto. Sin ninguno de los dos, la lógica de agente queda en `domain/` y `application/`, testeable sin frameworks.
- **Orquestación propia sin motor durable** (estado de la tarea en NATS KV, gestionado a mano): funciona, pero tras la caída de un pod hay que reconstruir a mano el punto exacto de la tarea, el trazado es manual y no hay mTLS entre agentes. Dapr Workflow resuelve las tres cosas con un estándar CNCF.
- **Dapr solo por el Dashboard:** el Dashboard no muestra la ejecución de cada tarea. El valor está en Workflow, el trazado automático y mTLS; la vista del flujo la dan las trazas.
- **NATS KV como almacén de estado de Dapr Workflow:** el almacén de JetStream no ofrece las transacciones que necesita el estado de actores y workflows (se confirma en la Fase 0). Redis sí, y es ligero.
- **Sustituir NATS por Redis Streams como broker:** se perdería el escalador de JetStream de KEDA y la mensajería ya diseñada. Redis solo guarda el estado de los workflows.
- **Argo Workflows para orquestar a los agentes:** define DAGs estáticos con un pod por paso. Aquí el flujo lo decide el modelo en tiempo de ejecución, y arrancar un pod por paso añade latencia y carga al scheduler. La UI que sí aporta valor es la de **Argo CD**, para la flota desplegada.
- **Terraform solo desde la laptop:** el lab dependería de una máquina concreta. `lab.yml` lo hace reproducible desde cualquier sitio, con `make` como respaldo.
- **Access keys de AWS en GitHub Secrets:** credenciales de larga duración en un repo público. OIDC da credenciales temporales ligadas al repo y al environment.
- **GitHub Actions aplicando manifiestos o `helm upgrade` en el cluster** (como el `cd.yml` de la referencia, por SSH): rompe GitOps y exigiría exponer el puerto 22 o el API server. La vuelta de información llega por Argo CD Notifications.
- **Un cluster o un namespace por estudiante:** más coste o más piezas sin mejorar el aislamiento para 3 ejercicios simples.
- **Lanzar contenedores desde la UI de Argo CD:** exigiría exponer Argo CD con HTTPS y SSO, y dejaría el despliegue fuera de Git.
- **Entorno permanente o stop en lugar de destroy:** costo.
- **Spot:** riesgo de interrupción en vivo.
- **AWS MCP:** cambios fuera de Terraform.

## Consecuencias

- **Positivas:**
  - Plataforma completa y reproducible con un comando.
  - Una carga agéntica realista que ejercita todas las capas.
  - Costo de infraestructura de unos pocos dólares.
  - Gasto LLM acotado por diseño y nulo en pruebas.
- **Negativas:**
  - Seis desviaciones del brief (§4), documentadas en el README.
  - Más servicios que mantener (4 agentes, gateway, fake, Dapr y Redis).
  - **Dapr consume capacidad de los workers:** un sidecar por réplica. Se fijan requests y límites del sidecar por annotation y se incluyen en el cálculo de capacidad (ADR-0002 §5). Su plano de control corre sin HA en el control plane.
  - El estado de los workflows en Redis se pierde con el `destroy`; es aceptable en un lab efímero.
  - La fidelidad de `fake-llm` limita lo que demuestran las pruebas de carga: valida la plataforma, no la calidad del modelo.
  - Hay dependencias externas el día de la demo: GitHub, `gcr.io`, `registry.k8s.io`, `quay.io`, Grafana Cloud y OpenAI (solo `live`).
  - Los paquetes de GHCR se hacen públicos a mano una vez.
  - Operar el lab depende de que GitHub Actions esté disponible (respaldo: `make up/down` local).
  - El rol de Terraform en AWS es amplio por naturaleza; se acota con OIDC por environment, prefijos de nombre y permissions boundary (ADR-0002 §2).
  - Instrumentar con OpenTelemetry añade código común en `agentlib` y consume parte de la cuota gratuita de trazas (se muestrea en las pruebas de carga).

## Verificación

- [ ] `terraform plan` vacío después de que el CA escale.
- [ ] `make down && make up` → todo `Synced/Healthy` sin pasos manuales.
- [ ] `.github/` no contiene `kubectl apply` ni `helm install`/`helm upgrade`.
- [ ] `cost-check.sh` en verde tras `make down`; Cost Explorer y el consumo de OpenAI dentro de lo estimado.
- [ ] `make local-up` ejecuta los escenarios 1–6 y 10 y la prueba de ataque sin AWS ni OpenAI.
- [ ] `lab.yml up` y `lab.yml down` funcionan desde GitHub sin credenciales AWS estáticas; un lab con más de `LAB_TTL_HOURS` encendido es destruido por `lab-reaper`.
- [ ] Un sync de Argo CD crea un GitHub Deployment y dispara `post-deploy.yml`, que queda en verde en el commit.
- [ ] Añadir un directorio en `gitops/apps/agents/` despliega un agente nuevo sin tocar ninguna otra pieza.
- [ ] Una tarea aparece en Grafana Cloud Traces como una sola traza que cruza orquestador, actividades del workflow, agentes, gateway y modelo.
- [ ] Matar el pod del orquestador a mitad de una tarea: otra réplica reanuda el workflow desde el último paso y no repite las llamadas al modelo ya completadas; solo puede repetirse la que estaba en curso (conteo en `llm_requests_total`).
- [ ] Dapr Dashboard muestra la flota y sus componentes; el historial de una instancia de workflow es consultable por `task_id`.
- [ ] En `main.yml`, ninguna acción va referenciada por etiqueta móvil, no hay `secrets: inherit` ni `:latest`, y un PR no publica imágenes.
- [ ] Ninguna imagen en ejecución viene de `docker.io`; las imágenes de los agentes no contienen `/bin/sh` (comprobado con `crane export`).
