# Guía de configuración: credenciales e infraestructura

Todo lo que hay que preparar para desplegar el laboratorio, en orden. Cada bloque indica qué se crea, para qué sirve, dónde se guarda y cómo se revoca.

> **Regla:** ningún token entra en Git ni en un chat. Los valores viven en un gestor de contraseñas y llegan al sistema por `seed-secrets.sh` (a SSM) o por la configuración de GitHub.

Los comandos son para **Git Bash**, desde la raíz del repo. En Windows, ejecuta primero:

```bash
export MSYS_NO_PATHCONV=1   # evita que Git Bash reescriba rutas como /agentic-platform/...
```

## Resumen de lo que se crea

| Proveedor | Elemento | Dónde termina |
|---|---|---|
| AWS | Bucket de estado, Budget, OIDC, 3 roles de GitHub | Terraform `bootstrap` |
| SonarCloud | `SONAR_TOKEN` | Secret del repo |
| Grafana Cloud | Token de Alloy y URLs | SSM `/agentic-platform/k8s/grafana-cloud` |
| Grafana Cloud | Token de service account | Secret del environment `observability` |
| OpenAI | API key de un proyecto con límite de 5 USD | SSM `.../openai-api-key` |
| LangSmith | API key | SSM `.../langsmith-api-key` |
| GitHub | GitHub App para Argo CD | SSM `.../github-app` |
| Local | Demo token, contraseñas de Redis y NATS | SSM (generados) |

## 0. Herramientas locales

```powershell
winget install Amazon.SessionManagerPlugin GitHub.cli jqlang.jq MikeFarah.yq astral-sh.uv k3d.k3d ezwinports.make koalaman.shellcheck
```

Después, `gh auth login`.

## 1. AWS: capa persistente

**Qué es:** bucket del estado de Terraform, alerta de presupuesto, confianza OIDC entre GitHub y AWS, y los roles que usan los workflows. No se destruye con el laboratorio.

```bash
cp infra/terraform/bootstrap/terraform.tfvars.example infra/terraform/bootstrap/terraform.tfvars
# Edita owner y budget_alert_emails (tu correo real)
bash infra/scripts/bootstrap.sh
```

Anota las salidas: `state_bucket`, `permissions_boundary_arn` y `github_role_arns` (tres roles).

- Confirma el correo de AWS Budgets si llega una solicitud.
- Activa Cost Explorer en la consola de Billing (gratuito).
- Conserva `infra/terraform/bootstrap/terraform.tfstate`: es local e ignorado por Git. Guarda una copia.

**Verificar:** `aws s3 ls | grep agentic-platform-tfstate`.

## 2. GitHub: ajustes del repositorio

*Settings → Actions → General*
- *Workflow permissions:* **Read repository contents**.
- *Fork pull request workflows:* **Require approval for all external contributors**.

*Settings → Advanced Security*
- Activa Dependabot alerts, Secret scanning y **Push protection**.

*Settings → Environments*: crea tres, todos con *Deployment branches* limitado a `main`.

| Environment | Revisores | Para qué |
|---|---|---|
| `lab` | **Tú** | Levantar y destruir el laboratorio |
| `lab-reaper` | Ninguno | Destruir por TTL sin esperar aprobación |
| `observability` | Ninguno | Dashboards de Grafana |

Variables (`gh` usa el repo del directorio actual):

```bash
BUCKET=<state_bucket>
gh variable set TF_STATE_BUCKET --body "$BUCKET"
gh variable set LAB_OWNER --body "andres"
gh variable set LAB_AMI_ID --body "ami-0d6dd9e8265d48906"     # Ubuntu 24.04, resuelta el 2026-11-08
gh variable set PERMISSIONS_BOUNDARY_ARN --body "<permissions_boundary_arn>"
gh variable set LAB_TTL_HOURS --body "6"
gh variable set AWS_ROLE_ARN --env lab --body "<rol lab de github_role_arns>"
gh variable set AWS_ROLE_ARN --env lab-reaper --body "<rol reaper>"
gh variable set AWS_ROLE_ARN --env observability --body "<rol observability>"
```

## 3. SonarCloud

**Para qué:** análisis de calidad en CI. Sin este token, `main.yml` sigue adelante, pero omite el análisis.

1. Entra en sonarcloud.io con GitHub e importa el repositorio.
2. Anota la clave de la organización (aparece en la URL, `sonarcloud.io/organizations/<clave>`) y la del proyecto. Este laboratorio usa `devops-platform-challenge` y `Andresm98_03-agentic-platform-swe`. Si difieren, ajusta `.github/workflows/_ci.yml`.
3. *Administration → Analysis Method:* desactiva **Automatic Analysis**.
4. *My Account → Security:* genera un token.

```bash
gh secret set SONAR_TOKEN
```

**Revocar:** *My Account → Security*.

## 4. Grafana Cloud

**Para qué:** métricas, logs, trazas y dashboards.

1. Crea una cuenta gratuita y un stack.
2. *Access Policies:* crea una política con `metrics:write`, `logs:write` y `traces:write`, y un token. Es `GRAFANA_CLOUD_TOKEN`.
3. En la página del stack anota URL y usuario numérico de:
   - **Prometheus:** URL completa de remote write (termina en `/api/prom/push`).
   - **Loki:** URL completa (termina en `/loki/api/v1/push`).
   - **OpenTelemetry:** endpoint OTLP (`https://otlp-gateway-<zona>.grafana.net/otlp`).
4. *Administration → Service accounts:* crea una con rol **Admin** y un token. Con **Editor** no puede crear el datasource y el workflow falla con 403.
5. *Connections → Add new connection:* busca `CloudWatch`, ábrelo y pulsa **Add new data source**. En *Settings*, elige el proveedor de autenticación **Grafana Assume Role** y anota el **ID de cuenta AWS de Grafana** y el **external ID** del cuadro de instrucciones. Son datos propios de tu instancia. Después **borra ese datasource temporal**: el definitivo lo crea `observability.yml`.

```bash
gh variable set GRAFANA_CLOUD_AWS_ACCOUNT_ID --body "<id-de-cuenta-de-grafana>"
gh variable set GRAFANA_CLOUDWATCH_EXTERNAL_ID --body "<external-id>"
gh variable set GRAFANA_URL --env observability --body "https://<tu-stack>.grafana.net"
gh variable set GRAFANA_CLOUDWATCH_ROLE_ARN --env observability --body "arn:aws:iam::972588015487:role/agentic-grafana-cloudwatch"
gh secret set GRAFANA_AUTH --env observability    # token de service account
```

## 5. OpenAI

**Para qué:** el modo `live`, solo con el token de demo. Las pruebas de carga usan `fake-llm`.

1. Crea un proyecto `agentic-platform-lab`.
2. Fija un **límite de gasto de 5 USD** en el proyecto. Si tu cuenta no lo permite por proyecto, hazlo en la organización.
3. En *Limits → Allow or block models*, elige **Allow only selected models** y activa solo `gpt-4o-mini` y `gpt-4.1-mini`, los únicos que admite el gateway. Usa esos nombres exactos, no las variantes con fecha.
4. Comprueba los precios y actualiza `LLM_ALLOWED_MODELS` en `gitops/apps/llm-gateway/values.yaml` si cambiaron. El modelo de cada agente es `LLM_MODEL` en `gitops/apps/agents/<agente>/values.yaml`.
5. Crea una API key del proyecto: `OPENAI_API_KEY`.

## 6. LangSmith

Crea una cuenta gratuita y una API key en *Settings → API Keys*: `LANGSMITH_API_KEY`. El proyecto `agentic-platform` aparece con las primeras trazas.

## 7. GitHub App para Argo CD

**Para qué:** que Argo CD informe a GitHub del resultado de cada despliegue.

*Settings → Developer settings → GitHub Apps → New GitHub App*
- *Webhook:* desactivado.
- *Repository permissions:* `Deployments` y `Commit statuses` en **Read and write**. Ninguno más.

Después:
1. Anota el **App ID**.
2. *Generate a private key* y guarda el `.pem` **fuera del repositorio**.
3. *Install App:* solo en este repositorio. El **Installation ID** es el número final de la URL.

## 8. Cargar los secretos en AWS

Crea un archivo **fuera del repositorio**, por ejemplo `~/agentic-secrets.env`:

```bash
OPENAI_API_KEY=
LANGSMITH_API_KEY=
GRAFANA_PROM_URL=
GRAFANA_PROM_USER=
GRAFANA_LOKI_URL=
GRAFANA_LOKI_USER=
GRAFANA_OTLP_URL=
GRAFANA_OTLP_USER=
GRAFANA_CLOUD_TOKEN=
GITHUB_APP_ID=
GITHUB_APP_INSTALLATION_ID=
GITHUB_APP_PRIVATE_KEY_FILE=/c/Users/<tu-usuario>/secure/agentic-app.pem
DEMO_TOKEN=          # genera con: openssl rand -hex 32. Guárdalo: lo usarás en la demo live
```

```bash
# tr quita los finales de línea de Windows, que se colarían dentro de los valores
set -a; source <(tr -d '\r' < ~/agentic-secrets.env); set +a
DRY_RUN=1 GENERATE_INTERNAL=1 bash infra/scripts/seed-secrets.sh    # no escribe nada
GENERATE_INTERNAL=1 bash infra/scripts/seed-secrets.sh
rm ~/agentic-secrets.env
```

`GENERATE_INTERNAL=1` genera las contraseñas de Redis y NATS. Se crean 12 parámetros.

**Verificar:** `aws ssm get-parameters-by-path --path /agentic-platform/k8s --recursive --query 'length(Parameters)'` → `12`.

## 9. Imágenes en GHCR

1. Relanza `main.yml` para analizar con `SONAR_TOKEN` el último commit:
   ```bash
   gh workflow run main.yml --ref main
   ```
2. Ejecuta el mirror: `gh workflow run mirror-images.yml --ref main`.
3. Comprueba que estos paquetes sean públicos. Si alguno no lo es, cámbialo en *tu perfil → Packages → Package settings*:
   - **Apps:** `orchestrator`, `researcher`, `analyst`, `executor`, `llm-gateway`, `fake-llm`.
   - **Mirror:** `mirror/traefik`, `mirror/nats`, `mirror/natsio/nats-server-config-reloader`, `mirror/natsio/prometheus-nats-exporter`, `mirror/redis`, `mirror/grafana/alloy`.

**Verificar:** desde una sesión sin login, `docker pull` de una imagen por su tag.

## 10. Dashboards

```bash
gh workflow run observability.yml --ref main
```

## 11. Primer despliegue

Antes de lanzarlo, crea la rama `stage`: sin ella, el ApplicationSet de ejercicios da error y Argo CD no queda sano.

```bash
git push origin main:stage
gh workflow run lab.yml --ref main -f action=up
```

Aprueba dos veces en GitHub: el plan y, tras revisarlo, el apply. El log muestra la URL del NLB. Guárdala:

```bash
gh variable set NLB_URL --body "http://<dns-del-nlb>"
```

La dirección cambia en cada despliegue. Para el túnel y las interfaces, usa `make tunnel` y los port-forward del README.

## 12. Ejercicios de estudiantes

1. La rama `stage` ya existe desde el paso 11.
2. Protege `stage` con un *ruleset*: PR con revisión obligatoria y **GitHub Actions en la lista de bypass**, porque CI escribe en `gitops/stage/`.
3. Tras publicar el primer ejercicio, haz público el paquete `exercises`.
4. Cuando cambie un workflow en `main`, llévalo a `stage` con un PR de `main` a `stage`.

## 13. Apagar y revocar

Al terminar cada sesión:

```bash
gh workflow run lab.yml --ref main -f action=down
```

Comprueba `cost-check` en el log y el gasto en Cost Explorer al día siguiente. Si se olvida, `lab-reaper` lo destruye a las 6 horas.

Al terminar el laboratorio, revoca:

| Elemento | Dónde |
|---|---|
| API key de OpenAI | Proyecto en OpenAI |
| API key de LangSmith | *Settings → API Keys* |
| Tokens de Grafana Cloud | *Access Policies* y *Service accounts* |
| Token de SonarCloud | *My Account → Security* |
| GitHub App | Elimina la clave privada o la App |
| Parámetros SSM | `aws ssm delete-parameters` bajo `/agentic-platform/k8s` |
| Capa persistente | `terraform destroy` en `infra/terraform/bootstrap` |
