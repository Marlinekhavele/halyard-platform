.PHONY: help install dev up down seed logs test test-unit test-e2e coverage lint format openapi migrate migration clean

help:            ## Show commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install:         ## Install every package plus test and lint tools
	pip install -r requirements-dev.txt

PORT ?= 8080

dev:             ## Run every service in one process (no Docker); PORT=8090 to change port
	python scripts/dev_server.py --port $(PORT)

seed:            ## Fill a running platform with demo shipments (same PORT as dev)
	python scripts/seed_demo.py --base http://localhost:$(PORT)

up:              ## Start the full microservice stack with Docker
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	docker compose --profile demo run --rm demo-seeder

down:            ## Stop the Docker stack
	docker compose down

logs:            ## Follow service logs
	docker compose logs -f accounts commercial operations billing notifications

test:            ## Run all tests (unit, API and end-to-end)
	python -m pytest -q

test-unit:       ## Run the per-package tests only
	python -m pytest -q packages services

test-e2e:        ## Run the end-to-end flow only
	python -m pytest -q tests/e2e

coverage:        ## Run all tests with coverage (fails under 90%); report in htmlcov/
	python -m pytest -q --cov --cov-report=term --cov-report=html

lint:            ## Check Google style: lint, docstrings, imports, formatting
	ruff check .
	ruff format --check .

format:          ## Apply formatting and safe lint fixes
	ruff format .
	ruff check --fix .

openapi:         ## Export every service's OpenAPI spec to docs/openapi
	python scripts/export_openapi.py

SERVICES := accounts commercial operations billing notifications

migrate:         ## Apply migrations for every service (uses each *_DATABASE_URL)
	@for s in $(SERVICES); do echo "== $$s"; (cd services/$$s && alembic upgrade head) || exit 1; done

migration:       ## New migration from model changes: make migration svc=billing m="add notes"
	@test -n "$(svc)" && test -n "$(m)" || (echo 'usage: make migration svc=<service> m="message"'; exit 1)
	cd services/$(svc) && alembic revision --autogenerate -m "$(m)"

clean:           ## Remove local dev data and caches
	rm -rf .dev .pytest_cache .ruff_cache
