FROM ghcr.io/astral-sh/uv:0.12.18 AS uv
FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core packages/core
COPY packages/server packages/server
COPY packages/cli packages/cli
COPY packages/sdk-python packages/sdk-python
COPY providers/mock providers/mock
RUN uv sync --frozen --all-packages --no-dev
COPY alembic.ini LICENSE ./
COPY examples examples
RUN useradd --create-home --uid 10001 openclass
ENV PATH="/app/.venv/bin:$PATH"

FROM base AS test
RUN uv sync --frozen --all-packages
COPY tests tests
USER openclass
CMD ["pytest", "-q", "-p", "no:cacheprovider", "--tb=short"]

FROM base AS runtime
USER openclass
EXPOSE 7331
CMD ["openclass", "serve", "--host", "0.0.0.0"]
