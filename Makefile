# Wise Mesh Continental — common commands. App: http://localhost:3010
COMPOSE := docker compose
DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: env up dev down reset logs db test-be test-fe e2e gen-api lint

env: ## create .env with a random JWT secret if it doesn't exist
	@test -f .env || (cp .env.example .env && \
	  sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=$$(openssl rand -hex 32)/" .env && rm -f .env.bak && \
	  echo "created .env")

up: env ## production-like stack (nginx + API + Postgres)
	$(COMPOSE) up -d --build
	@echo "App: http://localhost:3010   API docs: http://localhost:3011/docs"

dev: env ## hot reload: Vite (bun) on 3010 + uvicorn --reload
	$(DEV) up --build

down:
	$(COMPOSE) down

reset: env ## drop the database volume, then migrate and seed from scratch
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f api web

db: env
	$(COMPOSE) up -d db

test-be: db ## pytest against the mesh_test database
	cd backend && uv run pytest

test-fe:
	cd frontend && bun run check && bun run lint && bun run test

e2e: ## Playwright demo script against http://localhost:3010 (run `make reset` first)
	cd frontend && bunx playwright test

gen-api: ## OpenAPI schema -> frontend/src/lib/api/schema.d.ts
	cd backend && uv run python -m app.cli openapi openapi.json
	cd frontend && bun run gen:api

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && bun run lint && bun run check
