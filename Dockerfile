# One container: the SPA is built here and served by the same Python process that serves
# /api and /mcp. There is no separate frontend host.

# --- stage 1: build the SPA -----------------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# vite configs write to ../backend/static; inside the container we want it local.
# SPA first (emptyOutDir), then the MCP app bundles into its mcp-apps/ subdir.
RUN npm run build -- --outDir dist --emptyOutDir \
    && npm run build:apps -- --outDir dist/mcp-apps

# --- stage 2: the runtime -------------------------------------------------------------
FROM python:3.13-slim AS runtime
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, so code changes don't invalidate the layer.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ ./
COPY --from=frontend /build/dist ./static

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# Railway sets $PORT. Workers stay at 1 by default: scale with replicas first, and keep
# replicas x workers x pool_size inside Postgres's connection limit.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
