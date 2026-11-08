# ADR-0002: Identidad, credenciales, elasticidad y resiliencia ante carga y ataque

- **Estado:** Aceptado
- **Fecha:** 2026-11-07
- **Relacionado:** [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) · [ADR-0001](0001-plataforma-bootstrap-y-ciclo-de-vida.md)

## Contexto

- **Identidad y credenciales.** El AWS CCM, Cluster Autoscaler, External Secrets y KEDA forman la plataforma de control. Los tres primeros llaman a AWS, y K3s autogestionado **no tiene IRSA**. El CCM localiza instancias por nombre de nodo y el CA las asocia al ASG por `providerID`; si no casan, no hay autoscaling.
- **Exposición.** La demo es **pública** (NLB abierto). Una prueba de carga y un ataque se parecen desde fuera, y la arquitectura debe responder igual a ambos:
  - degradarse con control, sin caerse;
  - no superar 3 EC2;
  - **no consumir tokens del modelo real**.
- **La flota agéntica (ADR-0001 §3) tiene tres riesgos propios:**
  - la carga real es la cola, no la CPU;
  - un bucle de agente puede multiplicar las llamadas al modelo;
  - la API key es un secreto de alto valor.

## Decisión

### 1. Identidad del nodo, fijada en el bootstrap (IMDSv2)

```bash
--node-name="$(imds local-hostname)"                       # ip-10-0-1-23.ec2.internal
--kubelet-arg="cloud-provider=external"
--kubelet-arg="provider-id=aws:///$(imds placement/availability-zone)/$(imds instance-id)"
--node-label="platform.io/pool=apps"                       # agentes K3s
# server: --disable-cloud-controller --disable traefik,servicelb --node-taint CriticalAddonsOnly=true:NoExecute
```

- El CCM corre con `--controllers=cloud-node,cloud-node-lifecycle --configure-cloud-routes=false`:
  - las rutas las gestiona Flannel;
  - el NLB es de Terraform;
  - `cloud-node-lifecycle` borra el `Node` cuando el CA termina una instancia.
- Tag `kubernetes.io/cluster/agentic-platform=owned` en las instancias, las subnets y los SGs.
- Los nodos no dependen de Docker Hub (ADR-0001 §4): descargan en frío sin credenciales durante el scale-up.

### 2. Credenciales: un rol IAM por controlador y un único poseedor de la API key del LLM

```
role/agentic-cp-node (instance profile CP): SSM core, ssm:PutParameter(join token), sts:AssumeRole ↓
   ├─ role/agentic-ccm                 ec2:Describe*, ec2:CreateTags
   ├─ role/agentic-cluster-autoscaler  mutaciones condicionadas a la tag del ASG
   └─ role/agentic-external-secrets    ssm:GetParameter(s) en /agentic-platform/k8s/*
role/agentic-worker-node (workers): SSM core, ssm:GetParameter(join token) — nada más
```

- Cada controlador usa `AWS_CONFIG_FILE` con `role_arn` + `credential_source = Ec2InstanceMetadata`. Las credenciales son temporales y CloudTrail registra las llamadas por sesión.
- **Cluster Autoscaler:**
  - `SetDesiredCapacity` y `TerminateInstanceInAutoScalingGroup` solo sobre recursos con `k8s.io/cluster-autoscaler/agentic-platform=owned`;
  - los `Describe*` van sobre `*`, porque AWS no permite restringirlos.
- **GitHub Actions → AWS (OIDC, sin access keys):**
  - `role/agentic-github-actions` confía en `token.actions.githubusercontent.com` **solo** con `sub = repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:lab` (formato inmutable de GitHub). Ninguna rama, PR ni fork puede asumirlo.
  - El environment `lab` exige **tu aprobación** y solo lo usa `lab.yml`. `lab-reaper.yml` usa el environment `lab-reaper`, sin revisores, con un rol propio orientado a destruir. Los workflows de PR usan `pull_request` (nunca `pull_request_target`) y no tienen acceso al environment.
  - **Permisos:** los que Terraform necesita para EC2, ELBv2, Auto Scaling, SSM y el estado S3. IAM solo sobre roles e instance profiles con prefijo `agentic-*`, y obligando a una **permissions boundary**, para que no pueda crear un rol más poderoso que ella.
  - **Duración:** sesión de 1 h.
- **Argo CD → GitHub:**
  - **GitHub App** instalada solo en este repo, con permisos `Deployments: write` y `Commit statuses: write`; **sin acceso a contenido**.
  - Sus credenciales (app ID, installation ID y clave privada) viven en SSM y llegan al Secret de Argo CD Notifications vía ESO.
  - **Egress:** el namespace `argocd` puede salir a 443 para hablar con `api.github.com`.
- **API key de OpenAI:**
  - **Origen:** SSM, sincronizada por ESO en un Secret que **solo monta `llm-gateway`**.
  - **Clave de proyecto dedicado en OpenAI:** límite de gasto propio y modelos permitidos restringidos.
  - **Agentes sin key:** ningún agente la tiene y ningún log la imprime.
- **Dapr:** mTLS entre sidecars con certificados emitidos por Sentry; los componentes declaran `scopes` (qué `app-id` puede usarlos) y el pub/sub declara qué topics publica o consume cada `app-id`. Las credenciales de NATS y Redis llegan por ESO y solo las leen los sidecars.
- **NATS:**
  - un usuario por servicio, con permisos de publicación y suscripción limitados a sus subjects;
  - credenciales vía ESO;
  - un agente comprometido no puede publicar en subjects ajenos.

### 3. Aislamiento

| | IMDSv2 / hop limit | Taint / selector | Qué corre |
|---|---|---|---|
| Control plane (t3.large) | required / **2** | `CriticalAddonsOnly=true:NoExecute` | CCM, CA, ESO, KEDA, Argo CD, NATS, **Dapr control plane (sin HA) + Dashboard**, **Redis**, `fake-llm`, kube-state-metrics, Alloy metrics/eventos |
| Workers (t3.medium, ASG 1/1/2) | required / **1** | `platform.io/pool=apps` | DaemonSets (Traefik, Alloy logs, node-exporter), agentes (cada uno con su sidecar `daprd`) y `llm-gateway` |

- `fake-llm` corre en el control plane porque simula una **dependencia externa**: no debe consumir la capacidad de los workers que se mide.
- **NetworkPolicy, default-deny en `apps`.** Flujos permitidos:
  - DNS;
  - agentes → NATS;
  - agentes → `llm-gateway`;
  - Traefik → orquestador;
  - Alloy → métricas;
  - `llm-gateway` → `fake-llm`;
  - **solo `llm-gateway` → 0.0.0.0/0:443**, excepto IMDS y las redes privadas. La NetworkPolicy de K3s no filtra por dominio.
- **Imágenes distroless:** non-root, `readOnlyRootFilesystem`, `drop: ALL`, `seccompProfile: RuntimeDefault` y sin token de service account.
- **Herramientas cerradas:** el agente de ejecución solo invoca funciones de una lista cerrada; no tiene shell.

### 4. Exposición pública

- **NLB:**
  - SG con `TCP 80` desde `0.0.0.0/0`;
  - target group de tipo instancia en `:30080`, asociado al ASG;
  - cross-zone, deregistration de 30 s y health check `/ping` contra Traefik.
- **Workers:** solo aceptan `30080` desde el SG del NLB. Sin SSH ni 6443 público; se accede por Session Manager.
- **Traefik:**
  - DaemonSet con `externalTrafficPolicy: Local`, así que un worker nuevo pasa a *healthy* cuando su Traefik está listo;
  - `RateLimit` por IP y límite de body.
- **Superficie pública:** solo el orquestador (`POST /tasks`, `GET /tasks/{id}`) es público. Argo CD y Grafana se consultan por port-forward.

### 5. Elasticidad acotada

| Nivel | Configuración |
|---|---|
| Orquestador, investigador, análisis | KEDA `nats-jetstream` sobre `num_pending` de su consumidor (vía el endpoint de monitorización de NATS) |
| Investigador, análisis | Mínimo **0**, máximo según el límite de peticiones de la API del LLM |
| Ejecución | KEDA con **CPU 60 % + cola**, mínimo 1 y máximo 8 (requisito del brief); request 500m / limit 1000m; trabajo de CPU en un proceso aparte |
| `llm-gateway` | 2 réplicas fijas (PDB `minAvailable: 1`); no escala con la carga, porque es el punto de control |
| Nodo | CA por tags, `expander=least-waste`, `scale-down-unneeded-time=5m`, `skip-nodes-with-local-storage=false` |
| ASG | min 1 / max 2, `AZRebalance` suspendido, `cpu_credits=unlimited`, `enabled_metrics` |

- KEDA genera HPAs, así que la cadena Pending → CA → EC2 → NLB no cambia.
- **Sidecars de Dapr en la capacidad:** requests y límites fijados por annotation (punto de partida: 25m CPU / 48Mi request, 200m / 128Mi límite; se calibran en la Fase H). Se suman al request de cada réplica en el cálculo de cuántas caben por worker. El HPA por CPU del agente de ejecución mide el contenedor de la app (`containerResource`), no el sidecar.
- **Escalado a cero con Dapr:** el consumidor durable de JetStream existe antes que cualquier réplica (Job en sync-wave), así que los mensajes esperan en la cola y KEDA ve `num_pending` aunque no haya suscriptores.
- El agente de ejecución es el que llena los nodos y provoca los Pending (se calibra con el allocatable real).
- Con todo al máximo: **nunca más de 3 EC2, haya el tráfico que haya**.

### 6. Resiliencia ante carga y ataque, y contención del gasto LLM

**Principio:** el modo de una llamada al modelo lo decide la **arquitectura**, no quien hace la petición. Por defecto todo es simulado; el gasto real requiere superar **tres barreras independientes**.

```
Petición pública ──► Traefik (rate limit, body) ──► Orquestador (admisión)
                                                    │  sin X-Demo-Token válido → mode=simulated (siempre)
                                                    │  con token válido        → mode=live (marcado en el estado de la tarea)
Agentes ──► llm-gateway ──┬─► fake-llm  (mode=simulated | presupuesto agotado | circuito abierto | LLM_GLOBAL_MODE=simulated)
                          └─► OpenAI    (solo mode=live y presupuesto disponible y circuito cerrado)
```

| Barrera | Mecanismo | Qué protege |
|---|---|---|
| **1. Admisión** | `X-Demo-Token` (secreto en SSM vía ESO, comparación en tiempo constante) que solo tiene el operador. El tráfico público y k6 **nunca** obtienen `live`. | El público no puede elegir el modo |
| **2. Gateway** | Presupuesto global en **USD** (tokens × precio configurado por modelo) y peticiones por minuto en **NATS KV** (reserva atómica antes de la llamada y conciliación después), límite por tarea (pasos y tokens), timeout y reintentos con jitter, circuit breaker ante 429/5xx, interruptor `LLM_GLOBAL_MODE` en Git | Gasto, bucles de agente, fallos del proveedor |
| **3. Proveedor** | Proyecto OpenAI dedicado con límite de gasto de **5 USD** y modelos restringidos a la lista permitida | Último tope si fallan las dos anteriores |

Topes iniciales para **peticiones muy modestas** (se ajustan tras el test de contrato, con precios verificados en OpenAI):

| Parámetro | Valor | Motivo |
|---|---|---|
| Presupuesto global del gateway | **3 USD** | Deja 2 USD de margen bajo el límite del proyecto (5 USD) para tests de contrato y errores de cálculo |
| `max_tokens` por llamada | 300 (orquestador) / 200 (resto) | Respuestas breves y estructuradas |
| Entrada por llamada | ≤ 2.000 tokens (contexto recortado desde KV) | Evita que el historial crezca sin límite |
| Pasos por tarea | ≤ 6 llamadas al modelo entre todos los agentes | Corta bucles del orquestador |
| Tareas `live` | ≤ 5 por minuto y ≤ 50 en total por presupuesto | La demo necesita pocas |
| Modelos | Pequeños y económicos, uno por agente vía `LLM_MODEL` | Los elige el operador dentro de la lista permitida |

Patrones de resiliencia del resto de la plataforma:
- **Backpressure / load shedding:** el stream de JetStream tiene `max_msgs`/`max_bytes` con `discard=new`. Con la cola llena, el orquestador responde `429` o `503` con `Retry-After` en lugar de aceptar trabajo sin límite.
- **Bulkheads:** un consumidor, un Deployment, sus límites de recursos y su ScaledObject por agente. La saturación de uno no tumba a los otros.
- **Idempotencia y entrega:**
  - `task_id` como `Nats-Msg-Id` (deduplicación);
  - ack explícito, `ack_wait` mayor que el timeout del paso y `max_deliver`;
  - DLQ (`tasks.dead`) para los mensajes agotados.
- **Degradación:** si OpenAI falla o se agota el presupuesto, las tareas `live` siguen funcionando con `fake-llm` y quedan marcadas `degraded=true`.
- **`fake-llm`:**
  - **Compatible con la API de OpenAI y determinista:** guiones por rol, con *tool calls* incluidos, de modo que el orquestador ejecuta el mismo código.
  - **Latencia configurable:** distribución lognormal parametrizable.
  - **Inyección de fallos:** porcentaje de 429/500 y timeouts para pruebas de caos.
  - **Uso coherente:** devuelve el campo `usage`.
- **Métricas de control:** `llm_requests_total{agent,mode,model,outcome}`, `llm_tokens_total{agent,mode,direction}`, `llm_budget_remaining`, `llm_circuit_state` y `tasks_shed_total`. Alerta en Grafana si `llm_tokens_total{mode="live"}` crece sin una demo en curso.

## Alternativas descartadas

- **Rol OIDC confiando en cualquier rama del repo:** en un repo público, un PR malicioso podría intentar obtener credenciales. Se restringe al environment `lab` con aprobación.
- **PAT de GitHub con permiso de escritura en contenido para Argo CD:** podría hacer push al repo. La GitHub App solo escribe deployments y estados.
- **Instance profile único o access keys en un Secret:** cualquier pod hereda permisos, o quedan credenciales de larga duración.
- **IRSA casero o IAM Roles Anywhere:** demasiadas piezas para un lab.
- **Dejar que el CCM asigne el providerID por su cuenta:** abre una ventana de nodos fuera de grupo.
- **Modo `live`/`simulated` elegido por un parámetro del cliente:** un atacante lo pondría en `live`.
- **Límite de gasto solo en OpenAI:** se detecta tarde y deja la demo sin LLM de golpe; no hay degradación gradual.
- **Presupuesto en memoria de cada réplica del gateway:** con 2 réplicas el tope se duplica. NATS KV lo hace global sin añadir componentes.
- **Escalar el gateway con la carga:** multiplicaría el ritmo de llamadas al proveedor. El gateway es un cuello de botella **intencionado**.
- **Cola sin límite:** bajo ataque crece hasta agotar el disco del control plane.

## Consecuencias

- **Positivas:**
  - Una prueba de carga o un ataque es **observable y verificable**: el sistema escala hasta su techo, descarta trabajo con control y gasta **0 tokens reales**.
  - Mínimo privilegio en AWS, NATS y la API del LLM.
- **Negativas:**
  - El gateway es un punto crítico (2 réplicas + PDB) y añade latencia.
  - El plano de control de Dapr y Redis corren sin HA en el control plane: si caen, los workflows se pausan y se reanudan al volver, sin perder pasos ya persistidos.
  - Mantener `fake-llm` fiel a la API exige tests de contrato contra la API real, que se ejecutan a mano y con un presupuesto mínimo.
  - Si un controlador pierde su `nodeSelector` del control plane, no obtiene credenciales: falla de forma segura.
  - Los `Describe*` del CA quedan sobre `*`.

## Verificación

- [ ] Nodos con nombre `ip-…ec2.internal` y `providerID` `aws:///…`; ninguno conserva el taint `uninitialized`.
- [ ] Desde un pod de agente: IMDS da **timeout**, `api.openai.com` da **timeout** y el gateway responde.
- [ ] CloudTrail: `SetDesiredCapacity` lo hace `role/agentic-cluster-autoscaler`.
- [ ] Un workflow sin el environment `lab` (p. ej. un PR) falla al intentar asumir `role/agentic-github-actions`.
- [ ] `role/agentic-github-actions` no puede crear un rol IAM sin la permissions boundary (prueba con `iam:CreateRole`).
- [ ] Bajo carga: KEDA escala por cola → Pending → `TriggeredScaleUp` → nodo `Ready` → target `healthy`. Sin carga: escala a cero o al mínimo → `ScaleDown` → instancia terminada.
- [ ] **Prueba de ataque** (k6 con ráfagas, payloads grandes y un `X-Demo-Token` falso): `429` en el borde, `tasks_shed_total` sube, ASG ≤ 2, y **`increase(llm_tokens_total{mode="live"}[ventana]) == 0`**.
- [ ] **Prueba de caos** (`fake-llm` con 30 % de 5xx): el circuito se abre, las tareas terminan en reintento o DLQ y no se pierde ninguna (`task_id` contabilizado de extremo a extremo).
- [ ] **Caos de la orquestación:** `kubectl delete pod` del orquestador y de agentes en plena carga → los workflows se reanudan y todas las tareas terminan.
- [ ] Un sidecar con un `app-id` no autorizado no puede publicar en un topic ajeno (rechazo registrado).
- [ ] Presupuesto agotado en `live` → las tareas siguientes terminan `degraded=true` vía `fake-llm`.
