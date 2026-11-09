# Guía del viernes: despliegue, demostración y cierre

Guía para presentar la plataforma el viernes 13 de noviembre de 2026 **solo con un navegador**, desde una laptop sin herramientas instaladas. Se usan únicamente GitHub, la consola de AWS con CloudShell, Grafana y LangSmith.

**Idea central:** el sistema se despliega antes de empezar, y en cada capa activas su comportamiento delante del público.

## Qué está comprobado

Comprobado en AWS: arranque desde cero con `lab.yml up`, sin intervención manual; despliegue por GitOps; self-healing; una tarea completa por el NLB; KEDA escalando desde cero; un EC2 real unido por autoscaling; 2 destinos `healthy`; métricas y logs en Grafana; terminal por CloudShell, y un ejercicio de estudiante publicado y accesible en `/s/prueba/`.

| Sin comprobar | Consecuencia |
|---|---|
| Escritorio `ui-desktop` y sus accesos | Comprueba que abre antes de la presentación; las capturas son el plan B |
| Demos con k6 desde CloudShell | La capa de ataque tiene una alternativa sin k6 |
| Trazas en LangSmith | Compruébalas antes de mostrarlas |
| PR de un ejercicio desde un fork | Probado solo desde una rama del repositorio |

## Antes del viernes, desde la laptop

1. Entra en las cuatro webs: GitHub, AWS, Grafana y LangSmith. Comprueba también el MFA.
2. Abre CloudShell en `us-east-1` y confirma que funciona.
3. Guarda en un lugar accesible **capturas de Argo CD y Dapr Dashboard**, como plan B si el escritorio remoto falla.
4. Si puedes, ejecuta `up` y `down` una vez como ensayo. Cuesta menos de 1 USD.

No hagas cambios en `main` esa semana, ni fusiones los PR de Dependabot.

## Jueves por la noche: dejarlo todo listo

El laboratorio se levanta el jueves y queda encendido hasta la presentación. Encendido en reposo cuesta unos 0,17 USD por hora: **unos 2,50 USD por una noche de 14 horas**, además de lo que dure la presentación.

**Haz esto primero: amplía el tiempo de vida.** `lab-reaper` destruye el laboratorio a las 6 horas, así que sin este cambio no llegaría a la mañana. En GitHub, ve a *Settings → Secrets and variables → Actions → Variables* y cambia `LAB_TTL_HOURS` de `6` a `18`.

### Revisión por servicio

| Servicio | Qué comprobar | Dónde |
|---|---|---|
| **GitHub** | Puedes entrar; existen los environments `lab`, `lab-reaper` y `observability`; existe la rama `stage`; no hay PR de Dependabot fusionados | [Environments](https://github.com/Andresm98/03-agentic-platform-swe/settings/environments) y [Variables](https://github.com/Andresm98/03-agentic-platform-swe/settings/variables/actions) |
| **AWS** | Región `us-east-1`; EC2 sin instancias del laboratorio; los 12 parámetros bajo `/agentic-platform/k8s`; Budget activo | [SSM](https://us-east-1.console.aws.amazon.com/systems-manager/parameters/?region=us-east-1) y [Budgets](https://us-east-1.console.aws.amazon.com/billing/home#/budgets) |
| **Grafana** | La instancia abre; carpeta *Agentic Platform* con 6 dashboards; el token `agentic-alloy` no ha caducado | [Dashboards](https://andresm98.grafana.net/dashboards) y *Administration → Users and access → Cloud access policies* |
| **LangSmith** | Puedes entrar; la clave `agentic-lab-gateway` sigue activa | [Settings → API Keys](https://smith.langchain.com) |
| **OpenAI** | Solo si usarás el modelo real: saldo, *Auto recharge* desactivado y clave activa | [Facturación](https://platform.openai.com/settings/organization/billing/overview) |

### Levantar

1. Sigue la **Fase 1** completa, hasta que `make demo N=1` termine en `OK`.
2. Registra la URL del NLB: en *Variables*, crea o actualiza `NLB_URL` con el valor del resumen de la ejecución.
3. En Grafana, confirma que el dashboard *Kubernetes* muestra datos y que Loki devuelve líneas para `{namespace="apps"}`.
4. En CloudShell, envía una tarea, como en la capa de flota agéntica, y comprueba que llega a `completed`.
5. Levanta el escritorio con **`ui-desktop`** y comprueba que abre Argo CD, Dapr Dashboard y *Ejercicios* (ver [Abrir las interfaces](#abrir-las-interfaces-argo-cd-dapr-y-ejercicios)).
6. Deja el laboratorio encendido y cierra CloudShell. **No lances pruebas de carga esa noche.**

### Viernes por la mañana

CloudShell habrá cerrado la sesión. Treinta minutos antes de empezar:

1. Abre CloudShell y repite el **paso 4** de la Fase 1, omitiendo el `git clone` si la carpeta sigue ahí.
2. Ejecuta `kubectl -n argocd get applications` y `make demo N=1`.
3. Conéctate al escritorio con Fleet Manager y abre sus accesos.
4. Abre las pestañas de la Fase 2.

Si algo está roto a esa hora, no intentes recrearlo: un `up` completo no da tiempo. Usa el plan B.

## Fase 1: despliegue (jueves por la noche)

**1. Lanza el laboratorio.** En [Actions → lab](https://github.com/Andresm98/03-agentic-platform-swe/actions/workflows/lab.yml), pulsa **Run workflow**, con rama `main` y acción `up`.

**2. Aprueba dos veces.** En la ejecución, **Review deployments** → `lab` → **Approve and deploy**, una vez para el plan y otra para el apply. El plan debe decir `59 to add, 0 to destroy`. Desde aquí corre el coste, unos 0,20 USD por hora.

**3. Espera a que termine.** El resumen de la ejecución muestra la URL del NLB. Guárdala.

**4. Prepara CloudShell.** En la [consola de AWS, en us-east-1](https://us-east-1.console.aws.amazon.com/console/home?region=us-east-1), abre CloudShell. Pega **primero esta línea sola**, porque `sudo` se come lo que venga detrás:

```bash
sudo ln -sf "$(command -v python3)" /usr/local/bin/python
```

Después, este bloque. Si la carpeta ya existe de una sesión anterior, omite el `git clone`:

```bash
git clone https://github.com/Andresm98/03-agentic-platform-swe.git
cd 03-agentic-platform-swe
git pull
nohup bash infra/scripts/tunnel.sh </dev/null >/tmp/tunnel.log 2>&1 &
```

Espera 20 segundos y pega:

```bash
export KUBECONFIG=.lab/kubeconfig NO_COLOR=1
export NLB_URL="http://$(aws elbv2 describe-load-balancers --names agentic-platform-nlb --query 'LoadBalancers[0].DNSName' --output text)"
kubectl get nodes
kubectl -n argocd get applications
```

**5. Espera a que todo esté sano.** Repite el último comando hasta ver **21 aplicaciones `Synced` y `Healthy`**, incluida `exercise-prueba`. Puede tardar 30-45 minutos.

**6. Compruébalo:**

```bash
make demo N=1
```

Debe terminar en `OK`. Si es así, el sistema está listo.

**Importante:** CloudShell cierra la sesión tras 20-30 minutos sin actividad y corta el túnel. Si ocurre, repite el paso 4 sin el `git clone`, entrando antes en la carpeta con `cd 03-agentic-platform-swe`.

## Abrir las interfaces: Argo CD, Dapr y ejercicios

Argo CD y Dapr nunca se exponen a Internet. Se abren desde un escritorio Windows dentro de la VPC, en el navegador, con Fleet Manager. No necesitas `port-forward` ni túnel: la VM llega directamente a las interfaces y trae sus accesos en el escritorio. Cuesta unos céntimos por hora y requiere el laboratorio encendido.

**Ejecuta siempre primero `lab` y después `ui-desktop`.** Relanzar `lab.yml up` con el escritorio activo lo eliminaría.

1. En [Actions → ui-desktop](https://github.com/Andresm98/03-agentic-platform-swe/actions/workflows/ui-desktop.yml), pulsa **Run workflow**, con rama `main` y acción `up`. Aprueba una vez.
2. Espera unos 10 minutos a que Windows arranque. Está lista cuando este comando responde `Online`:

   ```bash
   aws ssm describe-instance-information --filters Key=tag:Name,Values=agentic-platform-ui-desktop --query 'InstanceInformationList[].PingStatus' --output text
   ```

3. En CloudShell, obtén la contraseña:

   ```bash
   aws ssm get-parameter --name /agentic-platform/cluster/ui-desktop-password --with-decryption --query Parameter.Value --output text
   ```

   Si responde `pending-bootstrap`, Windows aún no ha terminado: espera unos minutos y repítelo.

4. En AWS, ve a [Systems Manager → Fleet Manager](https://us-east-1.console.aws.amazon.com/systems-manager/fleet-manager/managed-nodes?region=us-east-1), selecciona la VM `agentic-platform-ui-desktop` y pulsa **Node actions → Connect → Connect with Remote Desktop**.
5. Elige la autenticación por usuario y contraseña, con el usuario `Administrator` y la contraseña del paso 3.
6. Usa los accesos del escritorio:

   | Acceso | Qué abre |
   |---|---|
   | **Argo CD** | Estado y sincronización de cada aplicación |
   | **Dapr Dashboard** | Apps, componentes y configuración de la flota |
   | **Ejercicios** | Una página con el enlace de cada ejercicio publicado; `prueba` abre su JSON de bienvenida |
   | **Actualizar ejercicios** | Regenera esa página si se ha publicado uno nuevo |

   El usuario de Argo CD es `admin`. Su contraseña inicial se obtiene en CloudShell, con el túnel abierto. Si ves `localhost:8080: connection refused`, falta la variable o el túnel:

   ```bash
   cd ~/03-agentic-platform-swe
   pkill -f session-manager-plugin; pkill -f tunnel.sh
   nohup bash infra/scripts/tunnel.sh </dev/null >/tmp/tunnel.log 2>&1 &
   sleep 20
   export KUBECONFIG=.lab/kubeconfig
   kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
   ```

La conexión se corta tras 10 minutos sin actividad y a los 60 minutos, y se puede renovar. Terraform destruye esta VM junto con el laboratorio en `lab.yml down`.

## Comprobación previa: trazas y escritorio

Hazla con el laboratorio encendido, después de la Fase 1, antes de dar nada por listo.

### Trazas de LangSmith

En CloudShell, ya con el túnel abierto:

```bash
cd ~/03-agentic-platform-swe && git pull
export KUBECONFIG=.lab/kubeconfig NO_COLOR=1
export NLB_URL="http://$(aws elbv2 describe-load-balancers --names agentic-platform-nlb --query 'LoadBalancers[0].DNSName' --output text)"
export DEMO_TOKEN=$(aws ssm get-parameter --name /agentic-platform/k8s/demo-token --with-decryption --query Parameter.Value --output text)
CONFIRM_LIVE=yes make demo N=15
```

| Comprobación | Resultado correcto |
|---|---|
| Salida de la demo | Termina en `OK` |
| [LangSmith](https://smith.langchain.com) → `agentic-platform` → **Tracing** → **Production**, tras 2 minutos | Llamadas `llm.orchestrator`, `llm.researcher` y `llm.executor` |

Si no aparecen trazas, la demo sigue siendo válida. Omite LangSmith en la presentación y muestra el dashboard *Agentes y LLM*.

### Escritorio

Contraseña de `Administrator` para conectarte, en CloudShell:

```bash
aws ssm get-parameter --name /agentic-platform/cluster/ui-desktop-password --with-decryption --query Parameter.Value --output text
```

Sigue [Abrir las interfaces](#abrir-las-interfaces-argo-cd-dapr-y-ejercicios) y comprueba:

| Acceso | Resultado correcto |
|---|---|
| Argo CD | Pide login y muestra las aplicaciones |
| Dapr Dashboard | Muestra la lista de aplicaciones |
| Ejercicios | Muestra el enlace `prueba`, que responde |

Haz en ese momento las **capturas de Argo CD y Dapr Dashboard**: son el plan B de la presentación.

## Fase 2: pestañas para la presentación

| Pestaña | Vista |
|---|---|
| CloudShell | Con el túnel activo |
| GitHub | Actions |
| AWS | EC2 → Instances, y Target Groups |
| Grafana | [Dashboards](https://andresm98.grafana.net/dashboards), carpeta *Agentic Platform* |
| Grafana Explore | Loki, con `{namespace="apps"}` |
| Fleet Manager | Escritorio con Argo CD, Dapr Dashboard y Ejercicios |

En Grafana, selecciona Loki `grafanacloud-andresm98-logs` y un rango de *Last 15 minutes*.

## Fase 3: demostración (unos 35 minutos)

Ejecuta todo en CloudShell, en la carpeta del repositorio.

| Min. | Capa | Acción |
|---|---|---|
| 0 | Introducción | Problema y arquitectura |
| 4 | Elasticidad | Lanzar el escalado y dejarlo corriendo |
| 5 | Infraestructura | Terraform y acceso sin SSH |
| 10 | GitOps | Self-healing |
| 15 | Flota agéntica | Tarea de principio a fin |
| 21 | Elasticidad | Mostrar el EC2 real |
| 26 | Resiliencia | Ataque |
| 30 | Observabilidad | Grafana |
| 33 | Ejercicios | Aplicación de un estudiante en vivo |
| 36 | Cierre | Conclusiones |

### Introducción

**Mensaje:** una plataforma Kubernetes autogestionada, efímera y reproducible, que ejecuta una flota de agentes de IA. Cada llamada al modelo cuesta dinero, así que un ataque no debe convertirse en una factura.

Muestra el [diagrama del README](../../README.md#arquitectura). Di desde el principio que tiene **un único control plane y no es alta disponibilidad**: es una decisión consciente para un laboratorio de coste mínimo.

### Elasticidad: lanzar

Tarda varios minutos, así que empieza ahora y sigue con las demás capas:

```bash
make demo N=7
```

### Capa: infraestructura

**Mensaje:** todo se crea con Terraform desde GitHub Actions, con OIDC y sin claves de larga duración.

Muestra en GitHub la ejecución de `lab.yml` con sus aprobaciones, y en AWS las instancias y el NLB. Explica que no hay SSH: el acceso es por Systems Manager, justo lo que usa tu túnel.

### Capa: GitOps

**Mensaje:** Git es la fuente de verdad, y GitHub Actions nunca toca el cluster.

Abre otra pestaña de CloudShell si la demo 7 sigue en marcha, y prepara la sesión con `cd 03-agentic-platform-swe` y los `export` de la Fase 1.

```bash
kubectl -n argocd get applications
make demo N=3
```

La demo borra un pod y altera las réplicas a mano, y el sistema se corrige solo. Míralo **en vivo en Argo CD**, desde el escritorio remoto, en la aplicación `fleet-llm-gateway`.

### Capa: flota agéntica

**Mensaje:** el modelo decide el flujo, y Dapr Workflow lo hace durable.

```bash
kubectl -n apps get deploy
TASK=$(curl -s -X POST "$NLB_URL/tasks" -H 'content-type: application/json' -d '{"goal":"Explica el autoscaling de la flota y su coste","complexity":2}')
echo "$TASK" | jq .
ID=$(echo "$TASK" | jq -r .task_id); echo "$ID"
```

Repite este comando hasta ver `completed`, que tardó 23 segundos en la prueba:

```bash
curl -s "$NLB_URL/tasks/$ID" | jq '{status, mode, degraded, summary, steps: [.steps[]? | {agent, status, pod}]}'
```

Muestra los tres agentes y el `pod` que atendió cada uno. Después, busca la tarea en Grafana Explore → Loki, sustituyendo el identificador:

```
{namespace="apps"} |= "<task_id>"
```

### Elasticidad: resultado

**Mensaje:** escala en dos niveles: pods y máquinas, con un máximo explícito de 3 EC2 para controlar el coste.

Cuando termine la demo 7:

```bash
make demo N=8
make demo N=9
kubectl get nodes
```

Muestra en AWS el nuevo EC2 y los 2 destinos `healthy`, y en Grafana el dashboard *Autoscaling*.

### Capa: resiliencia

**Mensaje:** ante un ataque, la plataforma rechaza tráfico en lugar de gastar dinero o caerse.

```bash
seq 1 300 | xargs -P 40 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X POST "$NLB_URL/tasks" -H 'content-type: application/json' -H 'X-Demo-Token: token-falso' -d '{"goal":"ataque","complexity":1}' | sort | uniq -c
```

Debes ver `429` junto a algunos `202`. Después, confirma que no se gastó nada:

```bash
kubectl -n apps port-forward svc/llm-gateway 18002:8000 >/dev/null 2>&1 &
sleep 3
curl -s http://localhost:18002/metrics | grep '^llm_tokens_total' | grep -c 'mode="live"'
kill %%
```

El resultado debe ser `0`: el token falso nunca llega al modelo real.

**No lances cargas largas.** Una rampa de 8 minutos saturó el cluster en la prueba.

### Capa: observabilidad

**Mensaje:** todo el sistema se ve en un solo lugar, por las 4 Golden Signals.

Muestra *Aplicación (4 Golden Signals)* y *Agentes y LLM*. Abre **Dapr Dashboard** en el escritorio remoto: se ven los agentes, sus sidecars y los componentes `pubsub` y `workflowstore`.

LangSmith registra el 100 % de las llamadas reales, pero solo el 1 % de las simuladas. En modo simulado es normal verlo casi vacío.

### Capa: ejercicios de estudiantes

**Mensaje:** un estudiante publica su contenedor con un Pull Request hacia `stage`, y la plataforma lo valida, lo escanea y lo despliega con sus propios controles.

Muestra en este orden:

1. En GitHub, el [PR del ejercicio de prueba](https://github.com/Andresm98/03-agentic-platform-swe/pull/9) y su ejecución de `exercises.yml`.
2. En Argo CD, en el escritorio remoto, la aplicación `exercise-prueba`.
3. El acceso **Ejercicios** del escritorio, que abre la aplicación publicada en `/s/prueba/`.

**Di:** corre sin root, con cuota de recursos y sin poder salir a Internet.

### Cierre

**Mensaje final:** todo se destruye y cualquiera puede recrearlo desde Git. Coste total del proyecto: unos 3-5 USD (estimado).

## Fase 4: apagar

Hazlo al terminar, sin esperar a nadie.

1. En [Actions → lab](https://github.com/Andresm98/03-agentic-platform-swe/actions/workflows/lab.yml), pulsa **Run workflow**, con rama `main` y acción `down`.
2. Aprueba dos veces. El plan debe decir `0 to add` y `59 to destroy`, u 11 más si el escritorio sigue activo: se destruye con el laboratorio.
3. Comprueba que la ejecución termine en verde, incluido `cost-check`.
4. Comprueba en AWS que EC2 no tiene instancias en ejecución.

5. Devuelve `LAB_TTL_HOURS` a `6` en las variables de GitHub.

`lab-reaper` destruye el laboratorio al superar `LAB_TTL_HOURS`, pero nunca se ha visto actuar: no dependas de él.

## Plan B

| Si falla | Haz esto |
|---|---|
| El `apply` falla | Lee el error y relanza `up`, con sus dos aprobaciones |
| Las aplicaciones no llegan a `Healthy` a tiempo | Presenta con capturas y explica la arquitectura |
| El escritorio remoto no abre | Muestra las capturas de Argo CD y Dapr, y su estado con `kubectl` |
| Se corta CloudShell o aparece `127.0.0.1:6443: connection refused` | Repite el paso 4; sigue con Grafana y AWS mientras tanto |
| El EC2 tarda demasiado | Continúa y vuelve a él antes de cerrar |
| `make demo` falla | Ejecuta el comando equivalente de `kubectl` y sigue |
| La API responde `503` | Explica que la plataforma rechaza trabajo al saturarse; pasa a Grafana |

## Preguntas probables

| Pregunta | Respuesta |
|---|---|
| ¿Por qué Argo CD va por un escritorio remoto? | Las consolas administrativas nunca se exponen a Internet: solo son accesibles dentro de la VPC |
| ¿Por qué K3s y no EKS? | Coste y control: EKS añade unos 73 USD al mes solo por el plano de control |
| ¿Qué pasa si cae el control plane? | Se pierde el cluster y se recrea desde Git. No es alta disponibilidad |
| ¿Qué impide gastar el presupuesto? | Token de admisión, 3 USD en el gateway y 5 USD en OpenAI |

## Lo que no debes afirmar

- Que es alta disponibilidad o un diseño de producción.
- Que escala sin límite: el máximo son 3 EC2.
- Cifras de coste como reales: son estimaciones hasta ver la factura.

## Modelo real

`LLM_GLOBAL_MODE: live` ya está activo en `main`. Sin `X-Demo-Token` válido, todas las tareas siguen en modo simulado. Gasta dinero real solo con ese token, con un tope de 3 USD, y una tarea consume unos 1750 tokens.

1. Hazlo en la capa de resiliencia, después de la ráfaga con token falso: el contraste es el mensaje.
2. Lee el token y ejecuta la demo en CloudShell:

   ```bash
   export DEMO_TOKEN=$(aws ssm get-parameter --name /agentic-platform/k8s/demo-token --with-decryption --query Parameter.Value --output text)
   CONFIRM_LIVE=yes make demo N=15
   ```

3. Muestra la llamada en [LangSmith](https://smith.langchain.com): entra en `agentic-platform`, abre **Tracing** con el entorno **Production** y recarga. Cada llamada aparece como `llm.orchestrator`, `llm.researcher` o `llm.executor`. Puede tardar un par de minutos, porque LangSmith procesa las trazas en segundo plano.
4. Después de la defensa, vuelve a `simulated` y revoca la clave de OpenAI.


***Notas***: cambios breves.
   ```bash
git add -A
git commit -m "name"
git pull --rebase origin main
git push origin main
   ```