.PHONY: setup check test dev db migrate
setup:
	uv sync --all-packages --locked
	npm ci
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	npm run format:check
	npm run typecheck
	npm test
test:
	uv run pytest
db:
	docker compose up -d db
migrate:
	uv run alembic upgrade head
dev:
	uv run openclass serve
