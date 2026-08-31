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
# The guard exists because this once shipped without the bundle: the SPA catch-all
# then serves index.html in its place and both hosts break with confusing CORS noise.
RUN npm run build -- --outDir dist --emptyOutDir \
    && APPS_OUT_DIR=dist/mcp-apps npm run build:apps \
    && test -s dist/mcp-apps/nutrition-day.html \
    && ! grep -q "assets/index" dist/mcp-apps/nutrition-day.html

# The icon set has to survive the build for the same reason the bundle does: these are
# the mark the browser tab, iOS, the launcher and Claude's connector all fetch by name,
# and a missing one degrades to a fallback icon rather than to a visible error.
RUN for i in favicon.ico apple-touch-icon.png icon-192.png icon-512.png \
             icon-maskable-512.png; do test -s "dist/$i" || exit 1; done

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
