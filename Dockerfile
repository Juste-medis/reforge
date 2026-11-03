# Re-Forge: one container serving the API and the built web UI on port 8000.
#   docker build -t reforge .
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v reforge-data:/app/data reforge
# The Meta Model API key comes from the environment at run time; it is never baked into the image.

FROM node:24.22.1-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/reforge ./reforge
RUN uv sync --frozen --no-dev
COPY assets /app/assets
COPY --from=ui /ui/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 reforge && mkdir -p /app/data && chown reforge /app/data
USER reforge
ENV REFORGE_HOST=0.0.0.0 REFORGE_PORT=8000 REFORGE_DATA_DIR=/app/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD [".venv/bin/reforge-api"]
