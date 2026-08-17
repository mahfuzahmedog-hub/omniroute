# Forge developer tasks.
# Usage: `make <target>`. Run `make help` for a list.

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
.PHONY: backend-install
backend-install: ## Install backend (editable) with dev extras
	cd backend && pip install -e ".[dev]"

.PHONY: backend-run
backend-run: ## Run the API with autoreload on :8000
	cd backend && uvicorn forge.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: migrate
migrate: ## Apply database migrations (alembic upgrade head)
	cd backend && alembic upgrade head

.PHONY: makemigration
makemigration: ## Autogenerate a new migration: make makemigration m="message"
	cd backend && alembic revision --autogenerate -m "$(m)"

.PHONY: test
test: ## Run the backend test suite
	cd backend && pytest -q

.PHONY: lint
lint: ## Lint + format-check the backend with ruff
	cd backend && ruff check forge tests

.PHONY: fmt
fmt: ## Auto-format the backend with ruff
	cd backend && ruff format forge tests && ruff check --fix forge tests

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
.PHONY: frontend-install
frontend-install: ## Install frontend dependencies
	cd frontend && npm install

.PHONY: frontend-dev
frontend-dev: ## Run the Vite dev server on :5173
	cd frontend && npm run dev

.PHONY: frontend-build
frontend-build: ## Type-check and build the frontend
	cd frontend && npm run build

# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------
.PHONY: db-up
db-up: ## Start local Postgres via docker compose
	docker compose up -d db

.PHONY: db-down
db-down: ## Stop local Postgres
	docker compose down
