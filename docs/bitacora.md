# Bitácora de despliegue

Registro de lo ejecutado durante el despliegue del laboratorio, en orden. Solo incluye hechos comprobados y nunca valores de secretos. La guía de cada paso está en [SETUP.md](SETUP.md).

## Estado

Última comprobación: 2026-11-08.

| Paso | Descripción | Estado |
|---|---|---|
| 1 | Herramientas locales y sesión de `gh` | Completado |
| 2 | Primer commit y push | Completado |
| 3 | Capa persistente de AWS | Completado |
| 4 | Ajustes de GitHub | Completado |
| 5 | SonarCloud | Completado |
| 6 | Grafana Cloud | Completado; el token se valida al ejecutar `observability.yml` |
| 7 | OpenAI | Completado; la clave se valida en la demo `live` |
| 8 | LangSmith | Completado; la clave se valida con las primeras trazas |
| 9 | GitHub App de Argo CD | Completado; se valida con el primer despliegue |
| 10 | Secretos en AWS | Completado |
| 11 | Mirror de imágenes | Pendiente |

| Área | Situación actual |
|---|---|
| Laboratorio en AWS | Sin desplegar: 0 instancias, 0 balanceadores |
| Parámetros SSM | 12, todos `SecureString` |
| Capa persistente | Creada y sin diferencias con Terraform |
| `origin/main` | `8ac56bc`, con los 6 servicios promovidos correctamente |
| Imágenes de las apps | 6 publicadas con el tag `2a1d194...`; el acceso sin login se comprobó en un tag anterior |
| Imágenes mirror | `traefik` disponible; `nats` incompleta (incidencia 2); el resto, sin copiar |
| Variables de GitHub | 5 de repositorio y `AWS_ROLE_ARN` en cada environment |
| Secretos de GitHub | `SONAR_TOKEN` (repositorio) y `GRAFANA_AUTH` (`observability`) |
| Environments de GitHub | `lab` (con aprobador), `lab-reaper` y `observability`, limitados a `main` |

## Dónde está cada cosa

Accesos para consultar la información. Aquí no se guarda ningún valor secreto.

### Consolas

| Servicio | Acceso | Qué se ve ahí |
|---|---|---|
| AWS (cuenta `972588015487`, región `us-east-1`) | [SSM Parameter Store](https://us-east-1.console.aws.amazon.com/systems-manager/parameters/?region=us-east-1) | Los 12 secretos del cluster; filtra por `/agentic-platform/k8s` |
| | [Bucket de estado](https://s3.console.aws.amazon.com/s3/buckets/agentic-platform-tfstate-972588015487) | Estado de Terraform del laboratorio |
| | [Budgets](https://us-east-1.console.aws.amazon.com/billing/home#/budgets) | Presupuesto `agentic-platform-monthly` |
| | [Cost Explorer](https://us-east-1.console.aws.amazon.com/costmanagement/home#/cost-explorer) | Gasto real |
| | [Roles IAM](https://us-east-1.console.aws.amazon.com/iam/home#/roles) | Roles `agentic-github-*` |
| GitHub | [Variables](https://github.com/Andresm98/03-agentic-platform-swe/settings/variables/actions) y [Secretos](https://github.com/Andresm98/03-agentic-platform-swe/settings/secrets/actions) | Configuración de los workflows |
| | [Environments](https://github.com/Andresm98/03-agentic-platform-swe/settings/environments) | `lab`, `lab-reaper` y `observability` |
| | [Actions](https://github.com/Andresm98/03-agentic-platform-swe/actions) | Ejecuciones y aprobaciones |
| | [Paquetes](https://github.com/Andresm98?tab=packages&repo_name=03-agentic-platform-swe) | Imágenes en GHCR |
| | [GitHub App](https://github.com/settings/apps/agentic-platform-argocd-andresm98) y [su instalación](https://github.com/settings/installations) | App ID, Installation ID y permisos |
| SonarCloud | [Proyecto](https://sonarcloud.io/project/overview?id=Andresm98_03-agentic-platform-swe) | Calidad del código |
| | [Organización](https://sonarcloud.io/organizations/devops-platform-challenge) | `devops-platform-challenge` |
| | [Tokens](https://sonarcloud.io/account/security) | Token `SONAR_TOKEN` |
| Grafana Cloud | [Portal](https://grafana.com/orgs/andresm98) | Stack; en *Details*, URLs y usuarios de Prometheus, Loki y OTLP |
| | [Instancia](https://andresm98.grafana.net) | Dashboards, carpeta *Agentic Platform* |
| | [Service accounts](https://andresm98.grafana.net/org/serviceaccounts) | Token de `GRAFANA_AUTH` |
| | *Instancia → Administration → Users and access → Cloud access policies* | Política y token `agentic-alloy` |
| OpenAI | [Plataforma](https://platform.openai.com), proyecto `agentic-platform-lab` | *Settings → Limits*: gasto y modelos; *API keys*: clave |
| | [Facturación](https://platform.openai.com/settings/organization/billing/overview) | Saldo y recarga automática |
| LangSmith | [Plataforma](https://smith.langchain.com) | *Settings → API Keys*: clave `agentic-lab-gateway`; proyecto `agentic-platform` con las trazas |

### Dónde vive cada secreto

GitHub y los proveedores no vuelven a mostrar un token ya creado. Si se pierde, se crea otro.

| Secreto | Dónde está guardado | ¿Se puede leer de nuevo? |
|---|---|---|
| Clave de OpenAI | SSM `/agentic-platform/k8s/openai-api-key` | Sí, en SSM |
| Clave de LangSmith | SSM `/agentic-platform/k8s/langsmith-api-key` | Sí, en SSM |
| Token de demo (`X-Demo-Token`) | SSM `/agentic-platform/k8s/demo-token` | Sí, en SSM |
| URLs, usuarios y token de envío a Grafana | SSM `/agentic-platform/k8s/grafana-cloud` (JSON) | Sí, en SSM |
| App ID, Installation ID y clave `.pem` de la GitHub App | SSM `/agentic-platform/k8s/github-app` (JSON) | Sí, en SSM |
| Contraseña de Redis | SSM `/agentic-platform/k8s/redis-password` (generada) | Sí, en SSM |
| Contraseñas de NATS, una por servicio | SSM `/agentic-platform/k8s/nats/<servicio>-password` (generadas) | Sí, en SSM |
| `SONAR_TOKEN` | Secreto del repositorio | No: se crea otro en SonarCloud |
| `GRAFANA_AUTH` | Secreto del environment `observability` | No: se crea otro en Service accounts |
| Estado de la capa persistente | `infra/terraform/bootstrap/terraform.tfstate`, local e ignorado por Git | Sí, conviene tener copia |

Para ver un secreto de SSM sin entrar en la consola, en **Git Bash** (cambia el nombre final):

```bash
MSYS_NO_PATHCONV=1 aws ssm get-parameter --name /agentic-platform/k8s/demo-token --with-decryption --query Parameter.Value --output text
```

Se puede usar también el botón *Show decrypted value* de la consola. No pegues el resultado en ningún chat.

## 2026-11-08

### Paso 1: herramientas locales

Instaladas con `winget`: `gh`, `jq`, `yq`, `uv`, `k3d`, `make`, `shellcheck` y `session-manager-plugin`. Ya estaban `aws`, `terraform`, `kubectl`, `helm` y `docker`.

**Comprobado:**
- Los 13 comandos están en el PATH.
- `gh` tiene sesión con la cuenta `Andresm98` y los permisos `repo` y `workflow`.
- `kubectl` vuelve a tener el contexto `docker-desktop`.

**Nota:** el token de `gh` no tiene `read:packages`, así que no puede listar los paquetes de GHCR. Se añade con `gh auth refresh -s read:packages` si hace falta.

### Paso 2: primer commit y push

Commit `40f6dcd` en `main`, con 400 archivos, enviado a `origin`.

**Comprobado:**
- `origin/main` recibió `40f6dcd` y, encima, el commit `28c457c` del bot de promoción.
- Ningún archivo versionado es `.pem`, `.tfstate`, `.tfvars` o `.env`.
- El repositorio es público.

| Workflow tras el push | Resultado | Detalle |
|---|---|---|
| `main` | Correcto | CI, escaneo IaC, 6 imágenes y promoción. El análisis de Sonar se omitió por falta de token |
| `observability` | Falló (esperado) | Todavía no hay rol de AWS configurado |
| `mirror-images` | Falló (no esperado) | Incidencia 2 |
| Dependabot | Correcto | Abrió 8 PR; incidencia 3 |

`main` terminó en verde, pero su promoción dejó un resultado incorrecto (incidencia 1).

### Paso 3: capa persistente de AWS

Creada con `bash infra/scripts/bootstrap.sh`, en la cuenta `972588015487`, región `us-east-1`.

**Comprobado:**
- `terraform plan` no detecta diferencias: `No changes`.
- Bucket `agentic-platform-tfstate-972588015487`: versionado activo, cifrado AES256 y acceso público bloqueado.
- Budget `agentic-platform-monthly` de 10 USD. El Budget `My Zero-Spend Budget` ya existía y no pertenece al laboratorio.
- Proveedor OIDC `token.actions.githubusercontent.com`.
- Política `agentic-boundary` aplicada a los tres roles.
- Cada rol solo confía en su environment de este repositorio:

| Rol | Environment |
|---|---|
| `agentic-github-actions` | `lab` |
| `agentic-github-reaper` | `lab-reaper` |
| `agentic-github-observability` | `observability` |

- `terraform.tfvars` y `terraform.tfstate` están ignorados por Git, y el correo de ejemplo ya no está.

**Sin poder comprobarlo desde aquí:** la copia de seguridad de `terraform.tfstate`, la confirmación del correo de AWS Budgets y la activación de Cost Explorer.

### Paso 4: ajustes de GitHub

**Correcto:**
- Commit `74fe3c0` en `main`. Su `main.yml` terminó bien y el bot promovió en `a3e5765`.
- Los 6 `values.yaml` tienen un solo documento y su propio tag `74fe3c0...`, igual que el Job de JetStream.
- Las 6 imágenes de ese tag se descargan sin login.
- Permisos de workflows en lectura y aprobación para colaboradores externos en PR de forks.
- Dependabot alerts, Secret scanning y Push protection activos.
- Variables `TF_STATE_BUCKET`, `LAB_OWNER`, `LAB_AMI_ID` y `LAB_TTL_HOURS`.

**Primer intento incompleto:** al ejecutar el bloque, `PERMISSIONS_BOUNDARY_ARN` y el `AWS_ROLE_ARN` de `observability` quedaron con el texto literal `$A:...`, y no se crearon `lab` ni `lab-reaper`. El `$A` literal indica que el bloque no se ejecutó en Git Bash: las variables y funciones de shell no se resolvieron, mientras que los `gh variable set` con valores fijos sí funcionaron.

**Comandos de la corrección.** Deben ejecutarse en **Git Bash**. No contienen secretos:

```bash
R=Andresm98/03-agentic-platform-swe
A=arn:aws:iam::972588015487
ME=$(gh api user --jq .id)

crear() {
  printf '{"reviewers":%s,"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' "$2" \
    | gh api -X PUT "repos/$R/environments/$1" --input - >/dev/null
  gh api -X POST "repos/$R/environments/$1/deployment-branch-policies" -f name=main -f type=branch >/dev/null
}

crear lab "[{\"type\":\"User\",\"id\":$ME}]"
crear lab-reaper null
crear observability null

gh variable set PERMISSIONS_BOUNDARY_ARN --repo "$R" --body "$A:policy/agentic-boundary"
gh variable set AWS_ROLE_ARN --repo "$R" --env lab --body "$A:role/agentic-github-actions"
gh variable set AWS_ROLE_ARN --repo "$R" --env lab-reaper --body "$A:role/agentic-github-reaper"
gh variable set AWS_ROLE_ARN --repo "$R" --env observability --body "$A:role/agentic-github-observability"
```

**Comprobado tras aplicarlos:**

| Environment | Protección | Ramas | `AWS_ROLE_ARN` |
|---|---|---|---|
| `lab` | Aprobación de `Andresm98` | `main` | `agentic-github-actions` |
| `lab-reaper` | Sin revisores | `main` | `agentic-github-reaper` |
| `observability` | Sin revisores | `main` | `agentic-github-observability` |

`PERMISSIONS_BOUNDARY_ARN` contiene ya el ARN real de `agentic-boundary`.

### Paso 5: SonarCloud

El proyecto se importó en una organización ya existente, no en una nueva.

| Dato | Valor |
|---|---|
| Organización | `devops-platform-challenge` (nombre visible: `devops_platform`) |
| Proyecto | `Andresm98_03-agentic-platform-swe` |

**Comprobado:**
- El proyecto existe y es público.
- El secreto `SONAR_TOKEN` existe en el repositorio.
- `_ci.yml` tenía la organización `andresm98`; se cambió a `devops-platform-challenge`, y se actualizó [SETUP.md](SETUP.md).

- El commit `8f8e295` pasó `main` completo y el bot lo promovió en `7191a77`.
- Primer análisis desde CI a las 19:50 UTC, sobre la revisión `8f8e295`. Esto confirma que el token sirve y que Automatic Analysis no interfiere.
- Quality gate **OK**, con cobertura del 91,2 %, 0 bugs, 8 vulnerabilidades y 44 code smells en 7172 líneas.

**Revisión de las 26 incidencias de seguridad** del análisis automático previo (19:43 UTC), que cubrió todo el repositorio:

| Incidencias | Hallazgo | Decisión |
|---|---|---|
| 2 (bloqueantes) | Instancias con IP pública | Decisión de diseño: subred pública sin NAT, por coste |
| 1 (bloqueante) | La app escucha en `0.0.0.0` | Necesario dentro de un pod; lo limita la NetworkPolicy |
| 1 | Inyección de argumentos en `exercises.py` | Falso positivo: argumentos en lista, sin shell, y los valores son SHA de GitHub |
| 15 | Instalación de paquetes sin `--only-binary` o `--no-build` | Sin cambios antes de la defensa |
| 4 | URL con `http://` en workflows y scripts | Sin cambios: el NLB del laboratorio solo sirve HTTP |
| 2 | Logs de acceso desactivados en S3 y NLB | Sin cambios: evita coste en un entorno efímero |
| 1 | Sin límite de almacenamiento en el contenedor | Sin cambios antes de la defensa |

Desde CI solo se analiza `apps/` (`sonar.sources=apps`), así que las incidencias de infraestructura dejarán de aparecer aunque sigan existiendo.

### Paso 6: Grafana Cloud

Stack `andresm98.grafana.net` en plan gratuito, región `prod-eu-west-6`. Política de acceso `agentic-alloy` con `metrics:write`, `logs:write` y `traces:write`.

**Comprobado:**
- La instancia responde en `/api/health`.
- Variables `GRAFANA_CLOUD_AWS_ACCOUNT_ID` (`008923505280`) y `GRAFANA_CLOUDWATCH_EXTERNAL_ID` en el repositorio.
- Variables `GRAFANA_URL` y `GRAFANA_CLOUDWATCH_ROLE_ARN`, y secreto `GRAFANA_AUTH`, en el environment `observability`.

**Aprendido:** Grafana solo muestra la cuenta y el External ID al crear un datasource CloudWatch con el proveedor **Grafana Assume Role**. Se creó uno temporal para leerlos. El error `AccessDenied` de *Save & test* es normal mientras no exista el rol. La guía se corrigió.

**Sin comprobar:**
- La validez de `GRAFANA_AUTH`, hasta ejecutar `observability.yml`.
- `GRAFANA_CLOUD_TOKEN` y las URL de envío, hasta que lleguen datos desde el cluster.
- El valor `authType = "grafana_assume_role"` para aprovisionamiento, que la documentación oficial no confirma.

### Paso 7: OpenAI

Proyecto dedicado, con solo `gpt-4o-mini` y `gpt-4.1-mini` permitidos y una API key propia. El gateway se ajustó a esos dos modelos en el commit `2a1d194` (incidencia 5).

La selección de modelos se comprobó con capturas de pantalla. El límite de gasto, la recarga automática desactivada y la clave no se pueden verificar desde aquí; los confirmó el operador.

### Paso 8: LangSmith

Se reutilizó una cuenta existente y se creó una clave específica, `agentic-lab-gateway`, en `Workspace 1`. No se puede verificar desde aquí: se confirmará cuando aparezca el proyecto `agentic-platform` con las primeras trazas. Sigue sin confirmar el nombre de la cabecera `Langsmith-Project`.

### Paso 9: GitHub App de Argo CD

App privada, creada e instalada por el operador. Una App privada no es visible en la API pública y la sesión de `gh` no puede listar instalaciones, así que sus permisos no se pudieron comprobar desde aquí. Se confirmará cuando Argo CD publique el primer estado en GitHub Deployments. La clave `.pem` no está en el repositorio.

### Paso 10: secretos en AWS

Cargados con `infra/scripts/seed-secrets.sh`, con las contraseñas internas generadas. El archivo de secretos se revisó solo en su forma, sin mostrar valores, y se borró al terminar.

**Comprobado por metadatos, sin descifrar:** existen los 12 parámetros, todos `SecureString`, en la versión 1 y con etiquetas.

**Sin comprobar:** que cada token sea válido en su servicio. Se confirma cuando el cluster los use.

### Incidencias

**1. La promoción GitOps corrompió los valores (corregida).** `_gitops-promote.yml` ejecutaba un solo `yq -i` con seis archivos, y `yq` fusiona todos en el primero.

- **Efecto:** `orchestrator/values.yaml` pasó de 43 a 228 líneas, con los seis servicios dentro. Los otros cinco siguieron con el tag `0.0.0-dev`, que no existe, y no habrían arrancado.
- **Por qué pasó en verde:** el comando no da error y el commit se hizo igualmente.
- **Corrección:** un `yq` por archivo. Se restauró `orchestrator/values.yaml`.
- **Comprobado en una copia de `gitops/`:** el comando extraído del workflow deja los 6 archivos con un solo documento y su propio tag. `helm template` renderiza correctamente el valor restaurado.
- **Confirmado en GitHub:** la promoción real de `74fe3c0` actualizó los 6 archivos sin mezclarlos.

**2. `mirror-images` denegado en GHCR.** `mirror/traefik` se copió completo. `mirror/nats` falló a mitad de copia, tras subir su primer manifiesto:

```
PUT .../mirror/nats/manifests/sha256:d7f535b0...: DENIED: requested access to the resource is denied
```

Al relanzarlo, `nats` y `nats-server-config-reloader` entraron, y el mismo error apareció en el siguiente paquete nuevo, `prometheus-nats-exporter`, también tras subir su primer manifiesto. El patrón apunta a un fallo intermitente de GHCR al crear un paquete nuevo, que se resuelve al reintentar. Se añadieron hasta 5 reintentos por imagen en `mirror-images.yml`; falta confirmarlo con una ejecución completa.

**3. PR de Dependabot.** Los PR #1 a #6 proponían subir la imagen de build de Python de `3.11` a `3.15`. Se cerraron porque la imagen final distroless usa Python 3.11 y ambas versiones tienen que coincidir. Los PR #7 (`checkov-action`) y #8 (`hatchling`) pasan CI y siguen abiertos. No se fusionan antes de la defensa, para no cambiar versiones ya probadas.

**4. Validación demasiado estricta del External ID (corregida).** El módulo `observability-aws` exigía al menos 8 caracteres y el External ID real de Grafana Cloud tiene 7, lo que habría hecho fallar `terraform plan` en `lab.yml up`. Ahora exige 2, el mínimo de AWS. `terraform validate` de `envs/lab` pasa con el cambio.

**5. Modelo no disponible en OpenAI (corregida).** El proyecto de OpenAI no ofrece `gpt-4.1-nano`, que estaba en la lista del gateway. Se sustituyó por `gpt-4.1-mini`, con su precio estándar real: 0,40 USD de entrada y 1,60 USD de salida por millón de tokens. Los cuatro agentes usan `gpt-4o-mini`, así que su comportamiento no cambia.

### Correcciones en la guía

Dos afirmaciones de [SETUP.md](SETUP.md) no coincidieron con lo observado y se corrigieron:
- Sin `SONAR_TOKEN`, `main.yml` no falla: omite el análisis.
- Los paquetes de GHCR de este repositorio público quedaron descargables sin login, sin cambiar su visibilidad a mano.
