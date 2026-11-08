# Validación de la flota agéntica y CI (equipo A)

Ejecutado el 2026-11-08 en local (Windows, Docker 29.8.2, Helm 4.1.4), sin AWS, sin OpenAI y sin commit ni push. Cada fila es un comando ejecutado con su resultado real. Lo no ejecutado está en [Pendiente](#pendiente).

## Código (`apps/`)

| Comando | Resultado |
|---|---|
| `apps/scripts/test.sh` (venv en Python 3.12) | rc=0. `ruff format --check`: 150 archivos ok. `ruff check`: sin errores |
| pytest por servicio, cobertura de ramas | agentlib 29 tests, 97 % · orchestrator 37, 93 % · researcher 5, 98 % · analyst 5, 96 % · executor 11, 97 % · llm_gateway 47, 88 % · fake_llm 14, 97 %. Total: 148 tests, ninguno falla |
| `apps/scripts/validate.sh` | rc=0 |
| `lint-imports` | 27 contratos respetados, 0 rotos |
| `mypy` estricto | Sin errores en 117 archivos |
| `uv export` frente a cada `requirements.txt` | Sincronizados con `uv.lock` |

Los tests corren en 3.12 y las imágenes en 3.11. La ejecución en 3.11 la cubre la prueba de punta a punta de abajo, no pytest.

## Imágenes y prueba de punta a punta (docker compose)

| Comando | Resultado |
|---|---|
| `docker run distroless/python3-debian12:nonroot -c "import sys..."` | Python 3.11.2 |
| `docker compose build` | 6 imágenes distroless, 185–212 MB |
| `docker compose up -d` + `apps/compose/smoke.sh` | La tarea recorre orquestador → researcher → executor → analyst con todos los pasos `ok`, `status=completed` y 0 series `mode="live"` |
| El mismo flujo con los **permisos NATS reales** de `gitops/platform/nats/values.yaml` y el `gitops/apps/dapr/pubsub.yaml` de producción (`envRef`, `publishingScopes`, `subscriptionScopes`) | Tarea completada. `Permissions Violation` en NATS: 0. Errores en los sidecars: 0. Consumidores con `pending=0` |
| Caída a mitad de tarea: `docker compose kill` de orquestador + sidecar con latencia del LLM de 3 s, tras 1 paso completado | El workflow se reanudó y terminó `completed` con los 3 pasos `ok`. 5 llamadas al modelo frente a 4 sin caída |

Lectura de la prueba de caída: la actividad en curso al morir el pod se reintentó (entrega al menos una vez). Las actividades ya persistidas no se repitieron. ADR-0001 pide no repetir "las llamadas ya hechas": se cumple para las completadas, no para la que estaba en vuelo.

Errores reales que encontró esta prueba y ya están corregidos:

- `BrokenProcessPool` en el agente de ejecución: el `WORKDIR` de distroless (`/home/nonroot`) no es accesible para la UID 10001 y `spawn` falla en `chdir`. Solución: `WORKDIR /app` en los 6 Dockerfile.
- `smoke.sh` daba OK aunque un paso fallara. Ahora exige `status=ok` en todos.

## Chart, GitOps y CI

| Comando | Resultado |
|---|---|
| `helm lint --strict` con los 6 values | OK |
| `helm template` con los 6 values | OK: analyst 8 objetos, executor 8, orchestrator 9, researcher 8, llm-gateway 7, fake-llm 5 |
| `kubeconform -strict -kubernetes-version 1.35.0` (6 releases + `gitops/apps/dapr`) | 54 recursos: 39 válidos, 0 inválidos, 0 errores, 15 omitidos (CRD sin esquema: Dapr, KEDA, ESO) |
| `kubectl kustomize gitops/apps/dapr` | OK; la imagen del Job se resuelve a `:0.0.0-dev` |
| `actionlint 1.7.7` sobre los 5 workflows | rc=0, sin hallazgos |
| Reglas de ADR-0001 §2 en `validate.sh` | Sin `secrets: inherit`, sin `:latest`, sin `kubectl apply`; todas las acciones fijadas por SHA de 40 caracteres |
| `git ls-remote` de cada acción | SHA resueltos al commit (`^{}` en tags anotados) |
| `k6 inspect` (`grafana/k6:1.8.2`) de los 6 escenarios | rc=0 |
| `bash -n` de las 10 demos y scripts | Sin errores de sintaxis |

## Verificado en el código fuente de Dapr

| Hecho | Fuente |
|---|---|
| `dapr-ext-workflow` 1.18.3 con `dapr` 1.19 emite `FutureWarning` por distribución legada: el workflow va dentro del wheel principal | Import real; `python -W error` limpio tras quitar el paquete |
| `AddConsumer` acepta un consumidor existente si coinciden ack, `ack_wait`, `max_deliver`, `max_ack_pending` y `deliver_policy` | nats.go `checkConfig`; probado en compose |
| `{appID}` en metadata, `envRef` y `dapr.io/env-from-secret` | dapr v1.19.1 `pkg/runtime/meta`, `pkg/apis/common`, `pkg/injector`; `envRef` probado en compose |
| LangSmith acepta OTLP en `https://api.smith.langchain.com/otel` con `x-api-key` | Documentación de LangSmith |

## Pendiente

**No ejecutado (requiere cluster o cuentas):**

- Chart y componentes en un cluster real: Argo CD, ESO, KEDA, NetworkPolicies, Ingress, mTLS con Sentry y `dapr.io/env-from-secret`.
- Las 10 demos: solo se comprobó su sintaxis.
- Los escenarios de k6: solo `inspect`; no se ha lanzado carga.
- Los workflows de GitHub: solo `actionlint`. El build a layout OCI, Trivy con `input` sobre ese layout, `crane push` y las attestations no se han ejecutado.
- Trivy sobre las imágenes.
- Exportación real a LangSmith y cualquier llamada a OpenAI.

**`TODO(verify)` en el repositorio:**

- Override de `cloudevent.id` por metadata en daprd 1.19.1 (de él depende la deduplicación `Nats-Msg-Id`).
- Redis como actor state store: compose usa 7.4; `gitops/platform/redis` puede usar 8.x.
- Precios por token en `llm-gateway`.
- Cabecera `Langsmith-Project` y mapeo de `langsmith.metadata.*`.
- `projectKey` y `organization` de SonarCloud.
- `NLB_URL`: el DNS del NLB cambia en cada `lab.yml up`.
