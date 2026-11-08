# Registro de validación

Evidencia **real** de cada fase del [plan](IMPLEMENTATION_PLAN.md#6-plan-por-fases). Regla: ninguna fase se marca como completada sin una entrada aquí con el comando ejecutado y su salida. Lo que no se pudo validar se escribe como tal, con el motivo.

Detalle por capa (lo escriben los equipos dueños):

- Plataforma e infraestructura: [`validation/platform.md`](validation/platform.md)
- Flota agéntica y CI: [`validation/fleet.md`](validation/fleet.md)

## Cómo registrar

1. Ejecutar el comando (o `make demo N=<n>`; los scripts imprimen timestamp UTC en cada línea).
2. Copiar la salida relevante, recortada, **sin secretos** (ni tokens, ni kubeconfig, ni ARNs de cuenta si no aportan).
3. Resultado: `OK`, `FALLA` (con el enlace a la corrección) o `NO VALIDADO` (con el motivo).
4. Si una corrección cambia el diseño, enlazar el commit y, si aplica, el ADR.

Plantilla de entrada:

````markdown
### <Fase>.<n> <qué se valida>

- **Fecha (UTC):** 2026-MM-DDTHH:MM:SSZ
- **Entorno:** local / compose / k3d / aws-lab
- **Commit:** `<sha>`
- **Comando:**

  ```bash
  <comando exacto>
  ```

- **Salida:**

  ```text
  <salida recortada>
  ```

- **Resultado:** OK | FALLA | NO VALIDADO
- **Notas:** <desviaciones, correcciones aplicadas, enlaces>
````

## Resumen por fase

| Fase | Criterio de salida (plan §6) | Estado | Última evidencia |
|---|---|---|---|
| 0 | `pytest` en verde; tarea e2e en compose con 0 tokens `live`; k3d `Synced/Healthy` y KEDA escala | Pendiente | |
| A | `terraform apply` ok; 2 instancias `Online` en SSM; 22 y 6443 cerrados; TG creado | Pendiente | |
| B | 2 nodos `Ready` por el túnel; `providerID` `aws:///`; user-data idempotente | Pendiente | |
| C | Sin taint `uninitialized`; CA descubre el ASG `min=1 max=2`; scale-up de humo | Pendiente | |
| D | Targets `healthy`; `curl /echo` 200 externo; ráfaga → `429`; 2 workers healthy | Pendiente | |
| E | `task_id` en todos los agentes; `nats stream info TASKS`; IMDS y OpenAI timeout desde pods; KEDA 0↔N | Pendiente | |
| F | Push → tag en Git → Argo sincroniza el SHA | Pendiente | |
| G | `helm lint` + `kubeconform`; `Synced/Healthy`; drift revertido | Pendiente | |
| H | Escenarios 4–11, 13–15 con timestamps y asserts | Pendiente | |
| I | Series, logs y trazas en Grafana Cloud con datos de la Fase H | Pendiente | |

## Fase 0: prerrequisitos y trabajo local

<!-- Entradas con la plantilla. Ejemplos: herramientas instaladas, pre-commit, pytest, compose e2e, k3d. -->

## Fase A: Terraform e infraestructura AWS

## Fase B: K3s

## Fase C: AWS CCM, Argo CD y Cluster Autoscaler

## Fase D: NLB y Traefik

## Fase E: agentes y NATS en el cluster

## Fase F: GitHub Actions + GHCR

## Fase G: endurecimiento de Helm y Argo CD

## Fase H: elasticidad, resiliencia y autoscaling de nodos

## Fase I: Grafana Cloud

## Verificación independiente previa a AWS (2026-11-08)

| Nivel | Comando | Resultado |
|---|---|---|
| 1 | `VALIDATE_HELM=1 infra/scripts/validate.sh` | rc=1 solo por bloqueo de archivo de Windows sobre el provider en `modules/network` y `modules/workers`. Ambos módulos los cubre `terraform validate` de `envs/lab`, que pasa. fmt, `bash -n`, YAML, kustomize y `helm template` OK |
| 1 | shellcheck, kubeconform (plataforma), tflint, checkov | **Sin ejecutar** |
| 2 | `apps/scripts/test.sh` | rc=0; cobertura ≥ 80 % en cada servicio |
| 2 | `apps/scripts/validate.sh` | rc=0 (import-linter, mypy, lint del chart) |
| 3 | `docker compose up -d --build` + `apps/compose/smoke.sh` | rc=0; tarea `completed`, 0 series `mode="live"` |
| 3 | `kill` de orquestador + sidecar a mitad de tarea y `up -d` | Tarea `completed` con 3 pasos, 0 series `live` |
| 4–5 | k3d y k6 | **Pendientes** (requieren k3d y memoria libre) |

Nota: `docker compose restart` no sirve para esta prueba. Con `network_mode: service`, el sidecar queda en la red del contenedor anterior. Hay que usar `kill` + `up -d` o `up -d --force-recreate`.

## Ejercicios de estudiantes (2026-11-08)

| Comprobación | Resultado |
|---|---|
| `python scripts/exercises/test_exercises.py` | 18 tests OK |
| `exercises.py plan` en un repo git desechable | PR válido, primer merge y retirada correctos; PR que toca fuera de su carpeta rechazado (rc=1) |
| `exercises.py sync` | Retira los values de un ejercicio eliminado |
| `helm lint --strict` y `helm template` con values de ejercicio | OK: sin Dapr, egress solo DNS, ingress desde Traefik y monitoring |
| Imagen `_ejemplo` con `--read-only --user 10001 --cap-drop ALL` | `/`, `/healthz`, `/readyz` y `/metrics` responden 200; `SIGTERM` limpio; 80 MB |
| `kind-smoke.sh` en kind con Pod Security `restricted` | Rollout correcto y rutas 200 |
| Regex de la política de imágenes | Acepta la imagen del workflow; rechaza `latest` y otros repos |

Sin probar: `exercises.yml` en GitHub Actions (no hay actionlint local), ApplicationSet, `AppProject`, `ValidatingAdmissionPolicy`, cuota y Traefik con prefijo en un cluster con Argo CD.

## Ejemplo de ejercicios en Go (2026-11-08)

`exercises/_ejemplo` pasó de Python a Go 1.27.3. `gofmt -l` sin diferencias; 18 tests del validador OK; imagen de 15,7 MB; con `--read-only --user 10001 --cap-drop ALL`, `/`, `/healthz`, `/readyz` y `/metrics` dan 200 y `/nope` 404; `SIGTERM` limpio; un test roto hace fallar el build; `kind-smoke.sh` correcto con Pod Security `restricted`.
