.PHONY: setup check test dev db migrate
setup:
	uv sync --all-packages --locked
	pnpm install --frozen-lockfile
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm run format:check
	pnpm run typecheck
	pnpm test
test:
	uv run pytest
db:
	docker compose up -d db
migrate:
	uv run alembic upgrade head
dev:
	uv run openclass serve
