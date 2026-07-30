.DEFAULT_GOAL := help
.PHONY: help setup db db-stop db-reset dev dev-backend dev-frontend migrate migrate-up \
        types test test-backend test-frontend lint fmt seed seed-reset build inspector clean

BACKEND  := backend
FRONTEND := frontend
ENV_FILE := $(BACKEND)/.env
# pgserver ships no cp313 wheel, so the dev database runs in its own throwaway 3.12 env.
DEVDB    := uv run --python 3.12 --with pgserver --no-project python scripts/devdb.py

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install

db: ## Start the local Postgres and write backend/.env
	@cd $(BACKEND) && url=$$($(DEVDB) start) \
		&& printf 'ENVIRONMENT=local\nDATABASE_URL=%s\nPUBLIC_URL=http://localhost:8000\n' "$$url" > .env \
		&& echo "Postgres up. DATABASE_URL written to $(ENV_FILE)."
	@$(MAKE) -s migrate-up

db-stop: ## Stop the local Postgres
	@cd $(BACKEND) && $(DEVDB) stop

db-reset: ## Destroy the local database and rebuild it from migrations
	@cd $(BACKEND) && $(DEVDB) stop || true
	rm -rf $(BACKEND)/.pgdata
	@$(MAKE) -s db

dev: ## Run backend + frontend + component-bundle watch together (http://localhost:5173)
	@echo "backend  → http://localhost:8000"
	@echo "frontend → http://localhost:5173  (proxies /api and /mcp to the backend)"
	@echo "mcp-apps → rebuilt on change (vite build --watch)"
	@trap 'kill 0' EXIT INT TERM; \
		( cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000 ) & \
		( cd $(FRONTEND) && npm run dev -- --port 5173 ) & \
		( cd $(FRONTEND) && npm run build:apps -- --watch --logLevel warn ) & \
		wait

dev-backend: ## Run only the backend, with reload
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run only the Vite dev server
	cd $(FRONTEND) && npm run dev

migrate: ## Autogenerate a migration: make migrate m="add workouts"
	@test -n "$(m)" || (echo 'usage: make migrate m="what changed"' && exit 1)
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"
	@echo "Review the generated file before committing — autogenerate misses renames,"
	@echo "server defaults and data migrations, and this runs against live traffic."

migrate-up: ## Apply migrations to the local database
	@cd $(BACKEND) && uv run alembic upgrade head

types: ## Regenerate the typed API client from the backend's OpenAPI schema
	cd $(BACKEND) && uv run python -m scripts.dump_openapi > ../$(FRONTEND)/openapi.json
	cd $(FRONTEND) && npm run generate:api

apps: ## Build the MCP app bundles (ui:// components) into backend/static/mcp-apps
	cd $(FRONTEND) && npm run build:apps

apps-dev: ## Preview ui:// components in FastMCP's dev UI (picker + AppBridge host, :8080)
	@cd $(FRONTEND) && npm run build:apps
	cd $(BACKEND) && PYTHONPATH=. uv run fastmcp dev apps app/mcp/server.py:mcp --mcp-port 8001

test: test-backend test-frontend ## Run everything CI runs

test-backend: ## ruff + pytest
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check . && uv run pytest -q

test-frontend: ## tsc + vitest
	cd $(FRONTEND) && npm run typecheck && npm run test

lint: ## Lint without fixing
	cd $(BACKEND) && uv run ruff check .

fmt: ## Format backend and frontend
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .

seed: ## Put sample data in the local database
	cd $(BACKEND) && uv run python -m scripts.seed

seed-reset: ## Wipe and re-seed sample data
	cd $(BACKEND) && uv run python -m scripts.seed --reset

build: ## Build the production container (requires Docker)
	docker build -t swolemates .

inspector: ## Open MCP Inspector against the local /mcp endpoint
	npx @modelcontextprotocol/inspector

clean: ## Remove build output and caches
	rm -rf $(BACKEND)/static $(BACKEND)/.venv $(FRONTEND)/node_modules $(FRONTEND)/dist
