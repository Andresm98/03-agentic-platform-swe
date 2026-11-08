# Versiones fijadas

Fuente única de las versiones del proyecto ([IMPLEMENTATION_PLAN.md §3](IMPLEMENTATION_PLAN.md#3-versiones-a-fijar)). Si una versión cambia aquí, cambia en Terraform, user-data, values de Argo CD, `pyproject.toml`/`uv.lock` y workflows.

- **Consulta:** 2026-11-07, con lectura de red sin credenciales: `update.k3s.io/v1-release/channels`, los `index.yaml` de cada repo de Helm, la API pública de releases de GitHub, PyPI, el registry de Terraform y `registry.k8s.io` (`HEAD` del manifest de la imagen).
- **Estado `verificada`:** la versión existe y es la indicada en la fecha de consulta. **No** significa que se haya probado en el cluster; eso queda en [`validation-log.md`](validation-log.md).
- **`TODO(verify)`:** no se comprobó. Hay que confirmarla antes de usarla.
- **Digests:** las imágenes se fijan por `@sha256:` en `platform-images.lock` (equipo P) y en los Dockerfile (equipo A). Esta tabla fija la versión; el digest se resuelve al hacer el mirror.

## Regla de la minor de Kubernetes

**K3s, AWS CCM y Cluster Autoscaler comparten la misma minor.** El CA y el CCM se compilan contra una versión concreta de la API de Kubernetes. Si las minors no coinciden, el comportamiento no está soportado.

| Línea | K3s | AWS CCM (chart · imagen) | Cluster Autoscaler (chart · imagen) | Estado |
|---|---|---|---|---|
| 1.34 (candidato original del plan, descartada) | `v1.34.13+k3s1` (canal `v1.34`) | chart `0.0.10` (appVersion `v1.34.0`) · imagen `v1.34.3` | chart `9.53.0` (appVersion `1.34.2`) · imagen `v1.34.6` | verificada |
| **1.35 (elegida el 2026-11-07)** | `v1.35.10+k3s1` (canal `v1.35`) | chart `0.0.12` (appVersion `v1.35.0`) · imagen `v1.35.3` | chart `9.59.0` (appVersion `1.35.0`) · imagen `v1.35.3` | verificada |

- El canal `stable` de K3s ya apunta a `v1.37.2+k3s1`. Para 1.36 y 1.37 no hay chart publicado del CCM (el último, `0.0.12`, es `v1.35.0`), así que la línea 1.37 obligaría a sobrescribir la imagen sobre un chart de otra minor.
- **Riesgo de soporte de 1.34:** según el calendario habitual de Kubernetes (unos 14 meses de soporte por minor), la 1.34 (agosto de 2025) estaría fuera de soporte upstream desde finales de octubre de 2026. `TODO(verify)`: fecha exacta de EOL de 1.34 en kubernetes.io/releases. Para un lab efímero el riesgo es bajo, pero **pasar a 1.35 cuesta lo mismo** (las tres piezas están verificadas). **Decisión tomada: 1.35.**
- La imagen del CCM y la del CA se sobrescriben en los values (`image.tag`) para usar el último parche de la minor; el chart se mantiene en la versión indicada.
- Las imágenes se comprobaron en `registry.k8s.io/provider-aws/cloud-controller-manager` y `registry.k8s.io/autoscaling/cluster-autoscaler` (HTTP 200 sobre el manifest).

## Plataforma (charts de Helm vía Argo CD)

| Componente | Chart · repo | Versión del chart | Versión de la app | Estado | Nota |
|---|---|---|---|---|---|
| Argo CD | `argo-cd` · `https://argoproj.github.io/argo-helm` | `10.15.0` | `v3.6.1` | verificada | Publicado el mismo día de la consulta; si se prefiere uno con rodaje, `10.12.1` (también `v3.6.1`) |
| Traefik | `traefik` · `https://traefik.github.io/charts` | `42.3.1` | `v3.7.17` | verificada | El plan decía "chart 3x.x": la serie actual es 42.x |
| NATS | `nats` · `https://nats-io.github.io/k8s/helm/charts/` | `2.15.2` | `2.15.2` | verificada | **Diferencia con el plan** (decía chart 1.x / NATS 2.11–2.12): el chart ahora sigue la versión del servidor. Confirmar que los values de JetStream no cambiaron |
| prometheus-nats-exporter | (subchart / imagen) | n/a | `0.20.2` | verificada (`platform-images.lock`) | Fijada por digest en el mirror |
| External Secrets | `external-secrets` · `https://charts.external-secrets.io` | `2.14.0` | `v2.14.0` | verificada | **Diferencia con el plan** (0.x/1.x): ya es 2.x; revisar la API de `ClusterSecretStore` (`external-secrets.io/v1`) |
| Grafana k8s-monitoring | `k8s-monitoring` · `https://grafana.github.io/helm-charts` | `4.6.0` | `4.6.0` | verificada | **Diferencia con el plan** (3.x): la 4.x cambia la estructura de values; decidir entre 4.6.0 o la última 3.x (`TODO(verify)`) |
| KEDA | `keda` · `https://kedacore.github.io/charts` | `2.21.0` | `2.21.0` | verificada | Escalador `nats-jetstream` + CPU |
| Dapr | `dapr` · `https://dapr.github.io/helm-charts/` | `1.19.1` | `1.19.1` | verificada | Imágenes en `ghcr.io/dapr` (`TODO(verify)` del tag exacto en GHCR) |
| Dapr Dashboard | `dapr-dashboard` · `https://dapr.github.io/helm-charts/` | `0.15.0` | `0.15.0` | verificada | |
| Cluster Autoscaler | `cluster-autoscaler` · `https://kubernetes.github.io/autoscaler` | ver tabla de la minor | | verificada | |
| AWS CCM | `aws-cloud-controller-manager` · `https://kubernetes.github.io/cloud-provider-aws` | ver tabla de la minor | | verificada | Se instala con el helm-controller de K3s, no con Argo CD |
| Redis (estado de Dapr Workflow) | imagen `redis` (mirror en GHCR) | n/a | `7.4.12` | verificada (`platform-images.lock`) | Fijada por digest en el mirror. `TODO(verify)` antes de subir a 8.x: que sea actor state store válido para Dapr 1.19 |

## Infraestructura y herramientas

| Componente | Versión | Estado | Nota |
|---|---|---|---|
| Terraform CLI | `1.17.1` (última); local `1.14.5` | verificada | El plan detectó 1.14.5 en la laptop. Fijar `required_version` y la versión de `setup-terraform` en CI a la misma |
| Terraform AWS provider | `6.72.0` (`~> 6.72`) | verificada | El exacto queda en `.terraform.lock.hcl` |
| Terraform Grafana provider | `TODO(verify)` | sin verificar | Para `observability/terraform` |
| AWS CLI v2 (user-data) | `2.39.6` | verificada (tag de GitHub `aws/aws-cli`) | Se instala con versión fijada en Ubuntu 24.04 |
| AMI Ubuntu 24.04 | `TODO(verify)` | sin verificar | Se resuelve una vez y se fija en una variable (plan §1.1 #21) |
| k3d | `v5.9.0` | verificada | |
| Helm | local `4.1.4`; última `v4.3.1` / `v3.22.1` | verificada | Los charts se prueban con Helm 4 |
| kubectl | local `1.36.1` | detectada en el plan | Dentro del skew permitido (±1 minor) solo si el cluster es 1.35+; con 1.34 hay 2 minors de diferencia. `TODO(verify)`: usar un kubectl 1.34/1.35 para la demo |
| k6 (imagen `grafana/k6`) | `1.8.2` | verificada | Existe la serie 2.x (`v2.3.0`); el plan pide 1.x |

## Runtime de las apps (Python)

| Componente | Versión | Estado | Nota |
|---|---|---|---|
| Imagen runtime | `gcr.io/distroless/python3-debian12:nonroot` por digest | `TODO(verify)` digest y minor de Python | debian12 trae Python 3.11; el builder debe ser `python:3.11-slim-bookworm`. Valorar `python3-debian13` (Python 3.13) |
| SDK `openai` | `3.46.0` | verificada (PyPI) | Fijado en `uv.lock` |
| SDK `dapr` | `1.19.0` | verificada (PyPI) | Debe ir con el runtime Dapr 1.19 |
| `dapr-ext-workflow` | `1.18.3` | verificada (PyPI) | **No hay 1.19 en PyPI** a la fecha. `TODO(verify)`: compatibilidad de `dapr-ext-workflow 1.18.3` con `dapr 1.19.0` y el runtime 1.19.1 (o fijar todo el SDK en 1.18.x) |
| `opentelemetry-api` / `opentelemetry-sdk` | `1.45.2` | verificada (PyPI) | |
| `opentelemetry-exporter-otlp` | `1.45.2` | verificada (PyPI) | |
| FastAPI, `nats-py`, `prometheus-client`, `pytest` | `TODO(verify)` | sin verificar | Las fija el equipo A en `uv.lock` |
| uv | `TODO(verify)` | sin verificar | |

## Hooks de pre-commit

Fijados por SHA en [`.pre-commit-config.yaml`](../.pre-commit-config.yaml).

| Hook | Tag | Commit | Estado |
|---|---|---|---|
| `pre-commit/pre-commit-hooks` | `v6.0.0` | `3e8a8703264a2f4a69428a0aa4dcb512790b2c8c` | verificada |
| `gitleaks/gitleaks` | `v8.30.1` | `83d9cd684c87d95d656c1458ef04895a7f1cbd8e` | verificada |
| `antonbabenko/pre-commit-terraform` | `v1.109.4` | `4c4437d784e93cacb1f05f1d7bc28e4354fafd20` | verificada |
| `astral-sh/ruff-pre-commit` | `v0.17.4` | `c0f278f1254ccc8fb09676bcdb8d847e7db493e5` | verificada |
| `hadolint/hadolint` | `v2.15.1` | `2eece55955ced00200be9729e9728cb7dacca505` | verificada |

## GitHub Actions

Se fijan por **commit SHA** en cada workflow (equipos P y A) y Dependabot las mantiene. No se listan aquí para no duplicar la fuente; `TODO(verify)` en cada workflow hasta resolver el SHA.

## Cómo reverificar

```bash
curl -sfL https://update.k3s.io/v1-release/channels | jq -r '.data[] | "\(.name) \(.latest)"'
helm repo add autoscaler https://kubernetes.github.io/autoscaler && helm search repo autoscaler/cluster-autoscaler --versions | head
curl -s https://api.github.com/repos/kubernetes/cloud-provider-aws/releases | jq -r '.[].tag_name' | head
curl -s https://pypi.org/pypi/dapr-ext-workflow/json | jq -r .info.version
```
