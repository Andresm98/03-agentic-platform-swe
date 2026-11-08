# Makefile: punto de entrada único. Cada target delega en un script versionado
# (contrato: docs/CONTRACTS.md §9). Si el script aún no existe, el target falla
# con un mensaje claro en lugar de hacer algo a medias.
#
# Uso: make help

SHELL         := bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE_FILE ?= apps/docker-compose.yml
DEMO_DIR     ?= scripts/demos
N            ?=

# $(call run,<script>,<args>): ejecuta el script con bash si existe; si no, error claro.
define run
	@if [ ! -f "$(1)" ]; then \
	  echo "ERROR: '$(1)' todavía no existe (ver docs/CONTRACTS.md §9 para saber qué equipo lo escribe)." >&2; \
	  exit 2; \
	fi; \
	bash "$(1)" $(2)
endef

# $(call need_compose): falla si no existe el docker-compose de las apps.
define need_compose
	@if [ ! -f "$(COMPOSE_FILE)" ]; then \
	  echo "ERROR: '$(COMPOSE_FILE)' todavía no existe (lo escribe el equipo A, docs/CONTRACTS.md §9)." >&2; \
	  exit 2; \
	fi
endef

.PHONY: help bootstrap seed-secrets up down tunnel cost-check local-up local-down \
        compose-up compose-down test validate lint demo demo-list

help: ## Muestra esta ayuda
	@echo "Agentic Platform: targets disponibles"
	@echo
	@grep -hE '^[a-zA-Z0-9_%-]+:.*## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'
	@echo
	@echo "Ejemplos: make demo N=7  |  make demo-07  |  make validate"

# --- Capa persistente (una sola vez) -------------------------------------------

bootstrap: ## Crea la capa persistente: bucket S3 de estado, OIDC, Budget
	$(call run,infra/scripts/bootstrap.sh)

seed-secrets: ## Carga los secretos externos en SSM Parameter Store (SecureString)
	$(call run,infra/scripts/seed-secrets.sh)

# --- Laboratorio AWS (efímero; preferir `gh workflow run lab.yml`) -------------

up: ## Levanta el lab en AWS desde local (terraform apply de envs/lab)
	$(call run,infra/scripts/lab.sh,up)

down: ## Destruye el lab en AWS y ejecuta cost-check
	$(call run,infra/scripts/lab.sh,down)

tunnel: ## Abre el túnel SSM al API server (127.0.0.1:6443) y trae el kubeconfig
	$(call run,infra/scripts/tunnel.sh)

cost-check: ## Falla si quedan recursos AWS del proyecto (EC2, LBs, EBS, EIPs, VPC...)
	$(call run,infra/scripts/cost-check.sh)

# --- Local (coste cero) ----------------------------------------------------------

local-up: ## Crea el cluster k3d local con Argo CD y gitops/clusters/local-k3d
	$(call run,scripts/local/k3d.sh,up)

local-down: ## Elimina el cluster k3d local
	$(call run,scripts/local/k3d.sh,down)

compose-up: ## Levanta la flota con docker compose (pruebas e2e locales)
	$(call need_compose)
	docker compose -f "$(COMPOSE_FILE)" up -d --build

compose-down: ## Para y elimina la flota de docker compose
	$(call need_compose)
	docker compose -f "$(COMPOSE_FILE)" down --remove-orphans

# --- Calidad -----------------------------------------------------------------------

test: ## Tests de las apps (ruff + pytest)
	$(call run,apps/scripts/test.sh)

validate: ## Validación estática: infra/plataforma (P) y apps/charts (A)
	$(call run,infra/scripts/validate.sh)
	$(call run,apps/scripts/validate.sh)

lint: ## Ejecuta todos los hooks de pre-commit sobre el repo
	@command -v pre-commit >/dev/null 2>&1 || { echo "ERROR: falta pre-commit (pipx install pre-commit)." >&2; exit 2; }
	pre-commit run --all-files

# --- Demos (docs/IMPLEMENTATION_PLAN.md §7) ---------------------------------------

demo: ## Ejecuta el escenario N (1..15): make demo N=7
	@if [ -z "$(N)" ]; then \
	  echo "ERROR: indica el escenario, p. ej. 'make demo N=7' (ver 'make demo-list')." >&2; exit 2; \
	fi; \
	if ! [[ "$(N)" =~ ^[0-9]+$$ ]]; then \
	  echo "ERROR: N debe ser un número entre 1 y 15 (recibido '$(N)')." >&2; exit 2; \
	fi; \
	nn=$$(printf '%02d' "$$((10#$(N)))"); \
	shopt -s nullglob; \
	matches=( $(DEMO_DIR)/$${nn}-*.sh ); \
	if [ $${#matches[@]} -eq 0 ]; then \
	  echo "ERROR: no existe '$(DEMO_DIR)/$${nn}-*.sh' todavía (dueño en docs/CONTRACTS.md §1)." >&2; exit 2; \
	fi; \
	if [ $${#matches[@]} -gt 1 ]; then \
	  echo "ERROR: hay más de un script para el escenario $${nn}: $${matches[*]}" >&2; exit 2; \
	fi; \
	echo ">> $${matches[0]}"; \
	bash "$${matches[0]}"

demo-%: ## Alias: make demo-07 equivale a make demo N=7
	@$(MAKE) --no-print-directory demo N=$*

demo-list: ## Lista los scripts de demo disponibles
	@shopt -s nullglob; found=0; \
	for f in $(DEMO_DIR)/[0-9][0-9]-*.sh; do echo "  $$f"; found=1; done; \
	if [ $$found -eq 0 ]; then echo "  (todavía no hay scripts de demo en $(DEMO_DIR))"; fi
