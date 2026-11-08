# Flota agéntica (`apps/`)

Seis servicios Python 3.11 (la minor de `gcr.io/distroless/python3-debian12`) sobre Dapr. Todos
siguen **Clean / Hexagonal** con la misma estructura en `src/<paquete>/`.

```
             adapters/inbound                 adapters/outbound
        FastAPI · Dapr sub · Workflow    OpenAI→gateway · Dapr pub/sub
                    │                     NATS KV · OTLP · Prometheus
                    ▼                                ▲ implementa
              application  ── casos de uso + puertos ┘
                    │
                    ▼
                  domain   (Python puro)

  bootstrap/ (composition root): el único que conoce todas las capas
```

| Capa | Contenido | Puede importar |
|---|---|---|
| `domain/` | Entidades, value objects, políticas, errores | Solo stdlib y `agentlib.domain` |
| `application/` | Casos de uso y puertos (Protocols) | `domain` y `agentlib.{domain,application}` |
| `adapters/inbound` | FastAPI, suscripciones y Workflow de Dapr | `application`, `domain` |
| `adapters/outbound` | Implementaciones de los puertos | `application`, `domain` |
| `bootstrap/` | Settings e inyección manual | Todo |

`import-linter` verifica estas reglas (`apps/pyproject.toml`, 27 contratos); `mypy` en modo estricto.

## Servicios

| Servicio | Puerto de entrada | Notas |
|---|---|---|
| `agents/orchestrator` | `POST /tasks`, `GET /tasks/{id}`, `agent.*.completed` | Dapr Workflow: el workflow es un generador de comandos en `application/workflow.py`; `adapters/inbound/dapr_workflow.py` solo los traduce |
| `agents/researcher` | `agent.research.requested` | Base de conocimiento en la imagen |
| `agents/analyst` | `agent.analysis.requested` | Puntuación determinista, publica `tasks.evaluated` |
| `agents/executor` | `agent.execution.requested` | Catálogo cerrado de CPU en `ProcessPoolExecutor(max_workers=1)` |
| `llm-gateway` | `POST /v1/chat/completions` | Único con API key: modo, presupuesto en NATS KV, circuito, LangSmith |
| `fake-llm` | `POST /v1/chat/completions`, `PUT /admin/faults` | Determinista, con inyección de fallos |
| `common/agentlib` | n/a | Puertos y adaptadores reutilizables, sin lógica de ningún agente |

## LangSmith

Activado por defecto (`LANGSMITH_ENABLED=true`). Exporta por OTLP, sin LangChain ni el SDK: `live`
al 100 %, simuladas con `LANGSMITH_SIMULATED_SAMPLE_RATE` (0.01). Es no bloqueante y *fail-open*:
un fallo solo incrementa `llm_telemetry_export_errors_total` y no afecta a readiness.

Local sin cuenta: `LANGSMITH_ENABLED=false make compose-up`. Sin API key el gateway también
desactiva la exportación, con un aviso en el log.

## Comandos

```bash
uv sync --all-packages        # entorno de desarrollo (apps/.venv)
apps/scripts/test.sh          # ruff + pytest, cobertura >= 80 % por servicio
apps/scripts/validate.sh      # import-linter, mypy, helm lint/template, reglas de CI
make compose-up && bash apps/compose/smoke.sh
```

Tras cambiar dependencias: `uv lock` y regenerar cada `requirements.txt` con
`uv export --frozen --no-dev --no-emit-workspace --package <svc> --python 3.11 --no-header`.
