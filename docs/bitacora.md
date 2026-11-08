# Bitácora de despliegue

Registro de lo ejecutado durante el despliegue del laboratorio, en orden. Solo incluye hechos comprobados y nunca valores de secretos. La guía de cada paso está en [SETUP.md](SETUP.md).

## Estado

Última comprobación: 2026-11-08.

| Paso | Descripción | Estado |
|---|---|---|
| 1 | Herramientas locales y sesión de `gh` | Completado |
| 2 | Primer commit y push | Completado |
| 3 | Capa persistente de AWS | Completado |
| 4 | Ajustes de GitHub | Pendiente |

| Área | Situación actual |
|---|---|
| Laboratorio en AWS | Sin desplegar: 0 instancias, 0 balanceadores, 0 parámetros SSM |
| Capa persistente | Creada y sin diferencias con Terraform |
| `origin/main` | `28c457c`, con la promoción defectuosa de la incidencia 1 |
| Corrección de la incidencia 1 | En local, pendiente de commit y push |
| Imágenes de las apps | 6 publicadas y descargables sin login, con tag `40f6dcd...` |
| Imágenes mirror | `traefik` disponible; `nats` incompleta (incidencia 2); el resto, sin copiar |
| Secretos y variables de GitHub | Ninguno configurado |
| Environments de GitHub | Solo `observability`, creado automáticamente y sin configurar |

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

### Incidencias

**1. La promoción GitOps corrompió los valores (corregida en local).** `_gitops-promote.yml` ejecutaba un solo `yq -i` con seis archivos, y `yq` fusiona todos en el primero.

- **Efecto:** `orchestrator/values.yaml` pasó de 43 a 228 líneas, con los seis servicios dentro. Los otros cinco siguieron con el tag `0.0.0-dev`, que no existe, y no habrían arrancado.
- **Por qué pasó en verde:** el comando no da error y el commit se hizo igualmente.
- **Corrección:** un `yq` por archivo. Se restauró `orchestrator/values.yaml`.
- **Comprobado en una copia de `gitops/`:** el comando extraído del workflow deja los 6 archivos con un solo documento y su propio tag. `helm template` renderiza correctamente el valor restaurado.
- **Falta:** confirmar la promoción real tras el próximo push.

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
