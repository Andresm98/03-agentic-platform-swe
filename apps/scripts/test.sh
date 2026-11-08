#!/usr/bin/env bash
# make test: ruff + pytest con cobertura >= 80 % por servicio (cada uno en su proceso: sus tests
# comparten nombres de módulo auxiliares).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -x .venv/Scripts/python.exe ]]; then BIN=.venv/Scripts; elif [[ -x .venv/bin/python ]]; then BIN=.venv/bin
else
  command -v uv >/dev/null || { echo "ERROR: falta uv y no existe apps/.venv" >&2; exit 2; }
  uv sync --frozen --all-packages
  BIN=.venv/bin
fi

"$BIN/ruff" format --check .
"$BIN/ruff" check .

fail=0
for svc in common/agentlib:agentlib agents/orchestrator:orchestrator agents/researcher:researcher \
           agents/analyst:analyst agents/executor:executor llm-gateway:llm_gateway fake-llm:fake_llm; do
  dir="${svc%%:*}"; module="${svc##*:}"
  echo "=== pytest $module"
  "$BIN/python" -m pytest "$dir/tests" --cov="$module" --cov-report=term --cov-fail-under=80 | tail -n 4 || fail=1
  [[ ${PIPESTATUS[0]} -eq 0 ]] || fail=1
done
exit "$fail"
