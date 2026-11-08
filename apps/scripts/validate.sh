#!/usr/bin/env bash
# make validate (parte A): capas, tipos, chart, sincronía de requirements y reglas de CI.
# Lo que necesita binarios ausentes se informa como SKIP, nunca como OK.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$(cd .. && pwd)"
fail=0
run() { echo "--- $*"; "$@" || { echo "FALLO: $*" >&2; fail=1; }; }

if [[ -x .venv/Scripts/python.exe ]]; then BIN=.venv/Scripts; SEP=";"; else BIN=.venv/bin; SEP=":"; fi

run "$BIN/lint-imports"
SRC="common/agentlib/src${SEP}agents/orchestrator/src${SEP}agents/researcher/src${SEP}agents/analyst/src${SEP}agents/executor/src${SEP}llm-gateway/src${SEP}fake-llm/src"
PYTHONPATH="$SRC" run "$BIN/mypy" common/agentlib/src/agentlib agents/orchestrator/src/orchestrator \
  agents/researcher/src/researcher agents/analyst/src/analyst agents/executor/src/executor \
  llm-gateway/src/llm_gateway fake-llm/src/fake_llm

UV="${UV:-$(command -v uv || true)}"
if [[ -n "$UV" ]]; then
  for s in agents/orchestrator:orchestrator agents/researcher:researcher agents/analyst:analyst \
           agents/executor:executor llm-gateway:llm-gateway fake-llm:fake-llm; do
    d="${s%%:*}"; p="${s##*:}"
    tmp="$(mktemp)"
    "$UV" export --frozen --no-dev --no-emit-workspace --package "$p" --python 3.11 --no-header -q -o "$tmp" \
      || fail=1
    diff -q <(tr -d '\r' <"$tmp") <(tr -d '\r' <"$d/requirements.txt") >/dev/null \
      || { echo "FALLO: $d/requirements.txt desincronizado de uv.lock" >&2; fail=1; }
    rm -f "$tmp"
  done
  echo "requirements.txt sincronizados con uv.lock"
else
  echo "SKIP: uv no disponible; no se comprobó requirements.txt contra uv.lock"
fi

CHART="$REPO/kubernetes/charts/agent-service"
if command -v helm >/dev/null; then
  shopt -s nullglob
  for f in "$REPO"/gitops/apps/agents/*/values.yaml "$REPO"/gitops/apps/llm-gateway/values.yaml "$REPO"/gitops/apps/fake-llm/values.yaml; do
    name="$(basename "$(dirname "$f")")"
    run helm lint "$CHART" -f "$f" --strict --quiet
    out="$(mktemp)"
    if helm template "$name" "$CHART" -n apps -f "$f" >"$out"; then
      echo "helm template $name OK ($(grep -c '^kind:' "$out") objetos)"
      if command -v kubeconform >/dev/null; then
        run kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.35.0 -summary "$out"
      else
        echo "SKIP: kubeconform no instalado ($name)"
      fi
    else
      echo "FALLO: helm template $name" >&2; fail=1
    fi
    rm -f "$out"
  done
else
  echo "SKIP: helm no instalado"
fi

# Reglas de ADR-0001 §2 sobre los workflows propios.
WF=("$REPO"/.github/workflows/{main,_ci,_images,_gitops-promote,post-deploy}.yml)
if grep -nE 'secrets:[[:space:]]*inherit|:latest\b|kubectl apply|helm (install|upgrade)' "${WF[@]}"; then
  echo "FALLO: patrón prohibido en los workflows" >&2; fail=1
fi
if grep -nE '^[[:space:]]*(- )?uses:[[:space:]]+[^.][^@]*@' "${WF[@]}" | grep -vE '@[0-9a-f]{40}([[:space:]]|$)'; then
  echo "FALLO: acción no fijada por SHA de commit" >&2; fail=1
fi
echo "Reglas de workflows comprobadas"

[[ "$fail" -eq 0 ]] && echo "validate (A): OK" || echo "validate (A): CON FALLOS" >&2
exit "$fail"
