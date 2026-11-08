# Scripts de demo

Cada escenario de la defensa ([IMPLEMENTATION_PLAN.md §7](../../docs/IMPLEMENTATION_PLAN.md#7-mapeo-de-escenarios-de-demo)) tiene un script que lo ejecuta y **comprueba el resultado** con asserts. Un escenario no se considera demostrado por haberlo visto en pantalla: se demuestra cuando su script termina con código 0.

## Ejecución

```bash
make demo N=7      # equivale a: bash scripts/demos/07-*.sh
make demo-07       # alias
make demo-list     # scripts disponibles
```

## Convención

- **Nombre:** `NN-nombre.sh`, con `NN` de dos dígitos igual al número del escenario (`01-deploy.sh` … `15-live.sh`). Un único script por número.
- **Dueño:** el equipo indicado en [CONTRACTS.md §1](../../docs/CONTRACTS.md#1-propiedad-de-directorios-quién-escribe-qué). P: 07, 08, 09, 11 y 12. A: 01–06, 10, 13, 14 y 15.
- **Cabecera obligatoria:**

  ```bash
  #!/usr/bin/env bash
  # NN-nombre.sh: <qué demuestra>. Evidencia: <qué comprueba>.
  set -euo pipefail
  source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
  require_cmd kubectl jq   # lo que use el script
  ```

- **Estructura:** una llamada a `step` por paso visible de la demo, asserts después de cada paso y `demo_summary` al final.
- **Códigos de salida:** `0` si todos los asserts pasan; `1` si falla un assert, un `wait_until` agota su tiempo o se llama a `die`; `2` en errores de uso. `set -euo pipefail` hace que cualquier comando que falle también termine el script.
- **Idempotentes y no destructivos fuera del escenario:** un script puede volver a ejecutarse; si crea carga o recursos de prueba, los limpia con `trap ... EXIT`.
- **Sin secretos:** los tokens (p. ej. `DEMO_TOKEN` para el escenario 15) se leen del entorno con `require_env`, nunca del script.
- **Evidencia:** toda línea lleva timestamp UTC. La salida se pega en [`docs/validation-log.md`](../../docs/validation-log.md) o se redirige con `make demo N=7 2>&1 | tee scripts/demos/out/07.log` (`out/` está en `.gitignore`).
- **Finales de línea:** LF (lo garantiza `.gitattributes`). Validar con `bash -n` y, si está disponible, `shellcheck`.

## Funciones de `lib.sh`

| Función | Uso |
|---|---|
| `log`, `info`, `warn` | Mensajes con timestamp |
| `die <msg>` | Error y salida con código 1 |
| `step <desc>` | Encabezado numerado de un paso |
| `require_cmd <cmd>...` | Falla si falta un comando |
| `require_env <VAR>...` | Falla si falta una variable de entorno |
| `assert_eq <actual> <esperado> [msg]` | Igualdad de cadenas |
| `assert_ge <actual> <mínimo> [msg]` / `assert_le` | Comparación numérica entera |
| `assert_contains <texto> <subcadena> [msg]` | Contiene |
| `wait_until <timeout_s> <cmd> [args...]` | Sondea cada `DEMO_POLL_SECONDS` (5 s) hasta que el comando sale con 0; falla al agotarse el tiempo |
| `ts`, `now_epoch`, `elapsed` | Timestamp ISO-8601 UTC, epoch y segundos desde el inicio |
| `demo_summary` | Resumen final con asserts superados y duración |

Variables: `NO_COLOR=1` desactiva el color (también se desactiva sin TTY), `DEMO_POLL_SECONDS` cambia el intervalo de sondeo y `DEMO_VERBOSE=1` muestra la salida de los comandos sondeados.

## Ejemplo

```bash
#!/usr/bin/env bash
# 08-node-join.sh: un worker nuevo se une a K3s. Evidencia: nodo Ready con providerID aws:///.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd kubectl

step "Esperar a que haya 2 workers Ready"
wait_until 600 bash -c '[ "$(kubectl get nodes -l platform.io/pool=apps --no-headers | grep -cw Ready)" -ge 2 ]'

step "Comprobar el providerID"
pid="$(kubectl get nodes -l platform.io/pool=apps -o jsonpath='{.items[-1].spec.providerID}')"
assert_contains "$pid" "aws:///" "providerID del nodo nuevo"

demo_summary
```
