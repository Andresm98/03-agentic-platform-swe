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
| 5 | SonarCloud | Falta el primer análisis real desde CI |

| Área | Situación actual |
|---|---|
| Laboratorio en AWS | Sin desplegar: 0 instancias, 0 balanceadores, 0 parámetros SSM |
| Capa persistente | Creada y sin diferencias con Terraform |
| `origin/main` | `a3e5765`, con los 6 servicios promovidos correctamente |
| Imágenes de las apps | 6 publicadas y descargables sin login, con tag `74fe3c0...` |
| Imágenes mirror | `traefik` disponible; `nats` incompleta (incidencia 2); el resto, sin copiar |
| Variables de GitHub | 5 de repositorio y `AWS_ROLE_ARN` en cada environment |
| Secretos de GitHub | `SONAR_TOKEN` |
| Environments de GitHub | `lab` (con aprobador), `lab-reaper` y `observability`, limitados a `main` |

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

**Sin comprobar:**
- Que Automatic Analysis esté desactivado: la API exige autenticación. El análisis de las 19:43 UTC no viene de CI y es anterior a la creación del token.
- Que el token tenga acceso a esta organización. Ambos puntos se confirman con el primer análisis desde CI.

**Revisión de las 26 incidencias de seguridad** de ese análisis automático, que cubrió todo el repositorio:

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

Causa sin confirmar. Como el primer manifiesto del mismo paquete entró con el mismo token, la hipótesis es un fallo transitorio de GHCR al crear un paquete nuevo. Se comprueba al relanzar el workflow en el paso de imágenes.

**3. PR de Dependabot.** Los PR #1 a #6 proponían subir la imagen de build de Python de `3.11` a `3.15`. Se cerraron porque la imagen final distroless usa Python 3.11 y ambas versiones tienen que coincidir. Los PR #7 (`checkov-action`) y #8 (`hatchling`) pasan CI y siguen abiertos. No se fusionan antes de la defensa, para no cambiar versiones ya probadas.

### Correcciones en la guía

Dos afirmaciones de [SETUP.md](SETUP.md) no coincidieron con lo observado y se corrigieron:
- Sin `SONAR_TOKEN`, `main.yml` no falla: omite el análisis.
- Los paquetes de GHCR de este repositorio público quedaron descargables sin login, sin cambiar su visibilidad a mano.
