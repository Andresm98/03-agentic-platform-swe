# Uso en vivo: seguimiento e2e de la plataforma

Cómo abrir las interfaces y seguir el sistema capa a capa con el laboratorio encendido. Sirve para ensayos y para la defensa.

> **Estado a 2026-11-08.** Están comprobados en AWS los nodos, Argo CD, Traefik, el NLB, los volúmenes, NATS, Redis, Dapr, External Secrets, una tarea completa por el NLB y las métricas en Grafana. **Falta comprobar** los logs y trazas, el escalado de nodos y los escenarios de demo. Si un paso falla, consulta [Diagnóstico rápido](#8-diagnóstico-rápido) y anótalo en la [bitácora](bitacora.md).

Todos los comandos son para **Git Bash**, desde la raíz del repositorio.

## 1. Antes de empezar

Comprueba que el laboratorio está encendido y cuánto le queda:

```bash
aws ec2 describe-instances --filters Name=tag:Project,Values=agentic-platform Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].[InstanceType,State.Name]' --output text
```

Debe mostrar una `t3.large` y al menos una `t3.medium`. El laboratorio cuesta unos 0,20 USD por hora, y `lab-reaper` lo destruye a las 6 horas de su creación. La hora de creación aparece en el resumen de la ejecución de `lab.yml`.

La URL del balanceador cambia en cada despliegue. Guárdala en cada terminal donde vayas a usarla:

```bash
export NLB_URL="http://$(aws elbv2 describe-load-balancers --names agentic-platform-nlb --query 'LoadBalancers[0].DNSName' --output text)"
echo "$NLB_URL"
```

## 2. Abrir el acceso

Cada bloque va en su propia terminal, y las terminales deben quedar abiertas.

**Terminal 1: túnel al API server.** Espera a ver `Waiting for connections...`.

```bash
bash infra/scripts/tunnel.sh
```

**Terminal 2: Argo CD.**

```bash
export KUBECONFIG=.lab/kubeconfig
kubectl get nodes
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n argocd port-forward svc/argo-cd-argocd-server 8080:80
```

**Terminal 3: Dapr Dashboard.**

```bash
export KUBECONFIG=.lab/kubeconfig
kubectl -n dapr-system port-forward svc/dapr-dashboard 8081:8080
```

**Terminal 4: comandos de seguimiento.** Ejecuta aquí el resto de esta guía.

```bash
export KUBECONFIG=.lab/kubeconfig
```

Si se corta un `port-forward`, relanza solo ese comando. Los accesos a cada consola están en la [bitácora](bitacora.md#dónde-está-cada-cosa).

## 3. Interfaces

| Interfaz | Dirección | Acceso | Para qué |
|---|---|---|---|
| Argo CD | <http://localhost:8080> | `admin` y la contraseña del paso 2 | Estado y sincronización de cada aplicación |
| Dapr Dashboard | <http://localhost:8081> | Sin login | Apps, componentes y configuración de la flota |
| Grafana | <https://andresm98.grafana.net/dashboards> | Cuenta de Grafana | Dashboards, logs y trazas |
| LangSmith | <https://smith.langchain.com>, proyecto `agentic-platform` | Cuenta de LangSmith | Llamadas al modelo |
| AWS | Enlaces en la [bitácora](bitacora.md#dónde-está-cada-cosa) | Cuenta de AWS | EC2, ASG, NLB y costes |
| API pública | `$NLB_URL/tasks` | Pública | Entrada de tareas |
| Ejercicios | `$NLB_URL/s/<nombre>/` | Pública | Contenedores de estudiantes |

En Argo CD, solo observa: no pulses *Sync* ni edites nada durante una demo. El estado deseado está en Git.

### Dashboards de Grafana

En la carpeta *Agentic Platform*:

| Dashboard | Qué mirar |
|---|---|
| Aplicación (4 Golden Signals) | Latencia, tráfico, errores y saturación |
| Agentes y LLM | Tokens por modo, USD gastados, presupuesto y circuito |
| Mensajería | Cola por consumidor, reentregas y mensajes |
| Autoscaling | Réplicas, escaladores KEDA y pods `Pending` |
| Kubernetes | Nodos, pods y reinicios |
| Infraestructura | Capacidad del ASG, CPU, memoria y disco |

## 4. Estado por capas

Recorre esta tabla de abajo arriba. Si una capa falla, las superiores también lo harán.

| Capa | Comando | Resultado correcto |
|---|---|---|
| Nodos | `kubectl get nodes` | Todos `Ready` |
| GitOps | `kubectl -n argocd get applications` | Todas `Synced` y `Healthy` |
| Secretos | `kubectl get externalsecret -A` | `SecretSynced` |
| Volúmenes | `kubectl get pvc -A` | Todos `Bound` |
| Pods con problemas | `kubectl get pods -A \| grep -vE 'Running\|Completed'` | Solo la cabecera |
| Datos | `kubectl -n nats get pods; kubectl -n data get pods` | `Running` y listos |
| Flota | `kubectl -n apps get deploy,scaledobject` | Réplicas listas y `READY=True` |
| Telemetría | `kubectl -n monitoring get pods` | `Running` y listos |
| NLB | Comando siguiente | `healthy` |

```bash
TG=$(aws elbv2 describe-target-groups --names agentic-platform-web --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --target-group-arn "$TG" \
  --query 'TargetHealthDescriptions[].[Target.Id,TargetHealth.State]' --output text
```

## 5. Seguir una tarea de principio a fin

Este recorrido usa `fake-llm`, así que **no gasta tokens reales**.

**1. Observa la flota.** En una terminal aparte:

```bash
export KUBECONFIG=.lab/kubeconfig
kubectl -n apps get pods -w
```

`researcher` y `analyst` empiezan en 0 réplicas. Al llegar trabajo, KEDA los arranca, así que la primera tarea tarda más.

**2. Envía la tarea:**

```bash
TASK=$(curl -s -X POST "$NLB_URL/tasks" -H 'content-type: application/json' \
  -d '{"goal":"Explica el autoscaling de la flota y su coste","complexity":2}')
echo "$TASK" | jq .
ID=$(echo "$TASK" | jq -r .task_id)
```

La respuesta correcta es `202`, con `task_id`.

**3. Consulta su avance** hasta que `status` sea `completed` o `failed`:

```bash
watch -n 3 "curl -s $NLB_URL/tasks/$ID | jq '{status, mode, degraded, steps}'"
```

Si `watch` no está disponible en tu terminal, repite el `curl`.

**4. Sigue la tarea por cada capa:**

| Etapa | Dónde | Cómo |
|---|---|---|
| Entrada | Traefik | `kubectl -n traefik logs daemonset/traefik --tail=20` |
| Workflow | Orquestador | `kubectl -n apps logs deploy/orchestrator -c orchestrator --tail=200 \| grep "$ID"` |
| Delegación | Cola de JetStream | Ver el bloque siguiente |
| Agentes | Logs | Cambia `orchestrator` por `researcher`, `analyst` o `executor` |
| Modelo | Gateway | Métricas del bloque siguiente |
| Logs agrupados | Grafana → Explore → Loki | `{namespace="apps"} \|= "<task_id>"` |
| Traza distribuida | Grafana → Explore → Tempo | Busca por servicio `orchestrator` |

**Cola de JetStream**, con los consumidores `orchestrator`, `researcher`, `analyst` y `executor`:

```bash
kubectl -n nats port-forward svc/nats 18222:8222 &
curl -s 'http://localhost:18222/jsz?consumers=true' | jq '.account_details[].stream_detail[]? | {name, messages: .state.messages, consumers: [.consumer_detail[]? | {name, num_pending, num_ack_pending, num_redelivered}]}'
```

**Métricas y presupuesto del gateway:**

```bash
kubectl -n apps port-forward svc/llm-gateway 18002:8000 &
curl -s http://localhost:18002/budget | jq .
curl -s http://localhost:18002/metrics | grep -E '^llm_(tokens_total|budget_remaining|circuit_state|requests_total)'
```

En modo simulado, ninguna línea de `llm_tokens_total` debe tener `mode="live"`. Al terminar, cierra estos procesos en segundo plano con `kill %1 %2`.

**Resultado esperado:** `status` en `completed`, con cada paso en `status: ok`, y `degraded` en `false`.

## 6. Observar la elasticidad

Abre estas vistas antes de generar carga:

```bash
kubectl -n apps get hpa,scaledobject -w
kubectl get nodes -w
kubectl get pods -n apps --field-selector=status.phase=Pending -w
```

El Cluster Autoscaler y el ASG se consultan así:

```bash
kubectl -n kube-system logs deploy/cluster-autoscaler-aws-cluster-autoscaler --tail=30
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names agentic-platform-worker \
  --query 'AutoScalingGroups[0].{min:MinSize,max:MaxSize,deseado:DesiredCapacity,instancias:Instances[].[InstanceId,LifecycleState]}'
```

La cadena esperada es: sube la cola → KEDA añade pods → pods `Pending` → el Cluster Autoscaler sube el ASG → nuevo nodo `Ready` → destino `healthy` en el NLB. Al bajar, el recorrido es inverso y puede tardar varios minutos.

Una ráfaga por encima del límite de Traefik debe devolver `429`, y una cola saturada, `429` o `503` con `Retry-After`.

## 7. Escenarios de demo

Requieren `KUBECONFIG` y `NLB_URL` exportados en esa terminal:

```bash
make demo-list
make demo N=1
```

La tabla completa está en el [README](../README.md#escenarios-de-demo). Guarda la salida como evidencia en el [registro de validación](validation-log.md).

### Modo con el modelo real

**Gasta dinero real.** Solo el escenario 15 lo usa, con un máximo de 3 USD en el gateway.

1. Cambia `LLM_GLOBAL_MODE` a `live` en `gitops/apps/llm-gateway/values.yaml`, haz commit y espera a que Argo CD sincronice.
2. Lee el token de demo sin dejarlo en el historial:

   ```bash
   export DEMO_TOKEN=$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --name /agentic-platform/k8s/demo-token --with-decryption --query Parameter.Value --output text)
   ```

3. Ejecuta la demo:

   ```bash
   CONFIRM_LIVE=yes make demo N=15
   ```

4. **Al terminar, vuelve a `simulated`** en Git y comprueba el gasto en el dashboard *Agentes y LLM*.

## 8. Diagnóstico rápido

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El túnel no conecta | Laboratorio apagado o credenciales de AWS caducadas | Revisa la sección 1 y `aws sts get-caller-identity` |
| `kubectl` no conecta | Túnel cerrado o falta `KUBECONFIG` | Relanza el túnel y exporta la variable |
| `/tasks` responde `404` | Orquestador aún sin desplegar | Revisa la aplicación de agentes en Argo CD |
| PVC en `Pending` | El helper de `local-path` no tolera el taint del control plane | Comprueba que `kubectl -n kube-system get cm local-path-config -o yaml` incluya `tolerations` |
| Argo CD reintenta un error ya corregido | Sigue con la revisión anterior hasta agotar sus reintentos | Espera unos minutos; la nueva revisión se aplica después |
| `llm-gateway` no está listo | NATS no disponible, o aún no se ejecutó el Job de JetStream | Revisa `fleet-dapr-components` y `kubectl -n apps logs deploy/llm-gateway -c llm-gateway --tail=50` |
| Alloy en `CrashLoopBackOff` | Configuración de destinos o credenciales | `kubectl -n monitoring logs <pod> -c alloy --previous --tail=30` |
| Grafana sigue vacío | Telemetría aún sin llegar, o token de envío incorrecto | Espera 5 minutos y revisa los logs de Alloy buscando `401` o `403` |
| `git push` rechazado | El bot promovió imágenes después de tu último `pull` | `git pull --rebase origin main` y repite el push |
| Dos ejecuciones de `lab.yml` | Se lanzó dos veces | Cancela la que está en `pending` con `gh run cancel <id>` |

El historial completo de fallos y correcciones está en la [bitácora](bitacora.md#incidencias), y la guía por fases, en el [runbook](runbook.md).

## 9. Apagar

Al terminar cada sesión:

```bash
gh workflow run lab.yml --ref main -f action=down
```

Aprueba en GitHub la ejecución. Después comprueba que `cost-check` termine bien en el log y revisa Cost Explorer al día siguiente. Cierra las terminales del túnel y de los `port-forward`.

Las credenciales se revocan solo al acabar el laboratorio; la lista está en la [guía de configuración](SETUP.md#13-apagar-y-revocar).
