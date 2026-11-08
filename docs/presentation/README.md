# Guion de la presentación por capas

Guía para presentar la plataforma el viernes 13 de noviembre de 2026, activando y demostrando cada capa en vivo. Duración prevista de la parte técnica: unos 40 minutos.

La idea central: **el sistema ya está arriba al empezar, y en cada capa activas su comportamiento delante del público.** El arranque completo se hace antes, porque es demasiado largo para hacerlo en directo.

Comandos y accesos detallados: [uso en vivo](../live-use.md). Evidencia: [registro de validación](../validation-log.md).

## Estado de cada capa

| Capa | Demostrado en AWS | Falta antes del viernes |
|---|---|---|
| 1. Infraestructura | Sí | Ensayo desde cero |
| 2. GitOps | Sí | Nada |
| 3. Flota agéntica | Sí, tarea real por el NLB | Comprobar la flota tras los ajustes de capacidad |
| 4. Elasticidad | Sí, EC2 real unido al cluster | Repetir desde 1 worker y comprobar el scale-down |
| 5. Resiliencia | No | Demos 13 y 14 |
| 6. Control de gasto y modelo real | No | Demo 15 |
| 7. Observabilidad | Métricas y logs | Trazas y LangSmith |
| 8. Ejercicios | No en el cluster | Publicar un ejercicio real por `stage` |

## Antes del viernes

**Regla:** después del ensayo, ningún cambio en `main`, ni siquiera los PR de Dependabot. La excepción es el cambio a modo `live`, descrito más abajo.

**Ensayo (martes o miércoles).** Haz `lab.yml up` desde cero, sin intervenciones manuales, y recorre este guion entero con cronómetro. Durante el ensayo:

- Captura pantallas de cada capa para el plan B: Argo CD, Grafana con el escalado, EC2 y NLB con 2 destinos.
- Guarda la salida de cada demo en un archivo.
- Apaga con `lab.yml down` al terminar.

**Modo real.** Cámbialo antes de desplegar, no durante la presentación: un commit en vivo lanza `main` y tarda unos 7 minutos.

1. Pon `LLM_GLOBAL_MODE: live` en `gitops/apps/llm-gateway/values.yaml`.
2. Haz commit y push, y espera a que `main` termine.
3. Sin `X-Demo-Token`, el tráfico sigue yendo a `fake-llm`. Compruébalo en el ensayo: la capa 5 depende de ello.
4. Al terminar la defensa, devuélvelo a `simulated`.

## El día de la presentación

### Dos horas antes

```bash
git pull --rebase origin main
gh workflow run lab.yml --ref main -f action=up    # aprueba el plan, revísalo y aprueba el apply
```

Cuando termine, copia la URL del NLB del resumen de la ejecución y regístrala:

```bash
gh variable set NLB_URL --body "http://<dns-del-nlb>"
```

### Treinta minutos antes

Abre las terminales del túnel y de los `port-forward` ([uso en vivo, sección 2](../live-use.md#2-abrir-el-acceso)). Después, en la terminal de demos:

```bash
export KUBECONFIG=.lab/kubeconfig
export NLB_URL="http://<dns-del-nlb>"
export NO_COLOR=1
make demo N=1
kubectl -n argocd get applications
kubectl get nodes
```

Debe haber 20 aplicaciones `Synced` y `Healthy`, y la demo 1 en verde.

Deja abiertas estas pestañas:

| Pestaña | Vista |
|---|---|
| Argo CD | Lista de aplicaciones |
| Dapr Dashboard | Applications |
| Grafana | *Autoscaling* y *Aplicación (4 Golden Signals)* |
| Grafana Explore | Loki, con `{namespace="apps"}` |
| AWS EC2 | Instancias y Target Groups |
| LangSmith | Proyecto `agentic-platform` |
| GitHub | Actions |

Lee el token de demo y déjalo solo en esa terminal:

```bash
export DEMO_TOKEN=$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --name /agentic-platform/k8s/demo-token --with-decryption --query Parameter.Value --output text)
```

## Desarrollo por capas

| Min. | Capa | Acción |
|---|---|---|
| 0 | Introducción | Problema y arquitectura |
| 4 | 4. Elasticidad, arranque | **Lanzar la demo 7** y dejarla corriendo |
| 5 | 1. Infraestructura | Terraform, red y acceso sin SSH |
| 10 | 2. GitOps | Self-healing en vivo |
| 15 | 3. Flota agéntica | Una tarea de principio a fin |
| 21 | 4. Elasticidad, resultado | Mostrar el EC2 real |
| 26 | 5. Resiliencia | Ataque |
| 31 | 6. Control de gasto | Tarea con el modelo real |
| 34 | 7. Observabilidad | Grafana y LangSmith |
| 37 | 8. Ejercicios | Contenedor de un estudiante |
| 39 | Cierre | Conclusiones y apagado |

### Introducción

**Mensaje:** una plataforma Kubernetes autogestionada, efímera y reproducible, que ejecuta una flota de agentes de IA. Cada llamada al modelo cuesta dinero, así que un ataque no puede convertirse en una factura.

**Muestra:** el [diagrama del README](../../README.md#arquitectura).

**Di desde el principio:** tiene un único control plane y no es alta disponibilidad. Es una decisión consciente para un laboratorio de coste mínimo.

### Elasticidad, arranque

La bajada y subida de nodos lleva minutos, así que se lanza ahora y se vuelve a ella después. En la terminal de demos:

```bash
make demo N=7
```

Crea pods de relleno que no caben en el worker. Continúa con las capas siguientes mientras tanto.

### Capa 1: infraestructura

**Mensaje:** todo se crea con Terraform desde GitHub Actions, con OIDC y sin claves de larga duración.

**Muestra:**

- GitHub Actions: la ejecución de `lab.yml`, con sus aprobaciones.
- AWS: instancias, ASG y NLB.
- Que no hay SSH: el acceso es por Systems Manager, como el túnel que estás usando.

**Pregunta probable:** «¿Por qué K3s y no EKS?». Coste y control: EKS añade unos 73 USD al mes solo por el plano de control.

### Capa 2: GitOps

**Mensaje:** Git es la fuente de verdad, y GitHub Actions nunca toca el cluster.

```bash
make demo N=3
```

**Muestra en Argo CD:** el pod borrado se recrea, y el cambio manual de réplicas se revierte solo. En el ensayo tardaron 7 segundos cada uno.

### Capa 3: flota agéntica

**Mensaje:** el modelo decide el flujo y Dapr Workflow lo hace durable.

Sigue los comandos de [uso en vivo, sección 5](../live-use.md#5-seguir-una-tarea-de-principio-a-fin). Envía la tarea y muestra:

- El `202` inmediato con su `task_id`.
- `researcher` y `analyst` arrancando **desde cero réplicas** con KEDA.
- `steps` con los tres agentes y el `pod` que atendió cada uno.
- La tarea en Grafana, filtrando por su `task_id` en Loki.

### Elasticidad, resultado

**Mensaje:** el escalado funciona en dos niveles: pods y máquinas.

**Muestra**, cuando la demo 7 haya terminado:

```bash
make demo N=8
make demo N=9
kubectl get nodes
```

Enseña en AWS el nuevo EC2, y en el NLB, los 2 destinos `healthy`. La bajada tarda unos 10 minutos y puedes mostrarla al final con `make demo N=11`.

**Di:** el máximo son 3 EC2, y es un límite explícito para controlar el coste.

### Capa 5: resiliencia

**Mensaje:** ante un ataque, la plataforma rechaza tráfico en lugar de gastar dinero o caerse.

```bash
make demo N=13
```

Genera ráfagas, cargas grandes y un `X-Demo-Token` falso. Muestra los `429` y el resultado clave: **0 tokens reales**.

Si sobra tiempo, `DURATION=1m make demo N=14` inyecta fallos en el modelo y borra orquestadores. Tarda unos 4 minutos más.

### Capa 6: control de gasto y modelo real

**Mensaje:** el modelo real existe, pero detrás de tres barreras.

```bash
CONFIRM_LIVE=yes make demo N=15
```

Muestra la tarea en LangSmith y el presupuesto restante, y explica las barreras: token de admisión, 3 USD en el gateway y 5 USD en OpenAI. Una sola tarea cuesta céntimos.

### Capa 7: observabilidad

**Mensaje:** se ve todo el sistema en un solo lugar, por las 4 Golden Signals.

**Muestra:** *Aplicación (4 Golden Signals)* durante el ataque, *Autoscaling* con el pico de réplicas, y *Agentes y LLM* con el presupuesto.

### Capa 8: ejercicios de estudiantes

**Mensaje:** cualquier estudiante publica su contenedor con un Pull Request, y la plataforma lo despliega con sus controles.

**Muestra:** el PR hacia `stage` y el contenedor en `$NLB_URL/s/<nombre>/`. Prepáralo antes de la presentación: es un flujo de varios minutos.

### Cierre

Resume qué se demostró y qué decisiones se tomaron. Después, apaga delante del público si hay tiempo:

```bash
gh workflow run lab.yml --ref main -f action=down
```

**Mensaje final:** todo se destruye, y cualquiera puede recrearlo desde Git. El coste total del proyecto se mantiene en unos 3-5 USD.

## Plan B

| Si falla | Haz esto |
|---|---|
| El despliegue no termina a tiempo | Presenta con las capturas y las salidas del ensayo |
| Se corta el túnel | Relánzalo y repite el `port-forward`; sigue mostrando Grafana y AWS mientras tanto |
| El EC2 tarda demasiado | Continúa y vuelve a él antes de cerrar |
| La API responde `503` tras la carga | Explica que es la plataforma rechazando trabajo; pasa a Grafana y sigue |
| El modelo real falla | Enseña la degradación a `fake-llm`: es parte del diseño |
| Falla Grafana | Muestra el mismo dato con `kubectl` |

## Lo que no debes afirmar

- Que es alta disponibilidad.
- Que escala sin límite: el máximo son 3 EC2.
- Que es un diseño de producción: es un laboratorio efímero, sin TLS en el NLB.
- Cifras de coste como reales: son estimaciones hasta ver la factura.
- Que una prueba de carga mide la calidad del modelo: usa `fake-llm`.

## Después de la presentación

1. Comprueba que `lab.yml down` y `cost-check` terminaron bien.
2. Devuelve `LLM_GLOBAL_MODE` a `simulated`.
3. Revoca los tokens según la [guía de configuración](../SETUP.md#13-apagar-y-revocar).
