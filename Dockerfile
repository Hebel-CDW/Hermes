# Hermes — single-container build: React UI + FastAPI, served on one port.
#   docker build -t hermes .
#   docker run -p 8000:8000 -v hermes-data:/data -e HERMES_DEMO_SEED=1 hermes
# See docs/HOSTING.md for the required environment and what is NOT production-ready.

FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app \
    HERMES_DB_PATH=/data/hermes.db
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# Install dependencies only. The app itself runs from /app via PYTHONPATH because
# taxonomy/ and data/ are resolved relative to the source tree, not site-packages.
RUN pip install . && pip uninstall -y hermes

COPY api ./api
COPY scripts ./scripts
COPY taxonomy ./taxonomy
COPY infra ./infra
COPY config/client_names.example ./config/client_names.example
COPY data/fixtures ./data/fixtures
COPY --from=web /web/dist ./web/dist

RUN useradd --system --uid 10001 --home /app hermes \
    && mkdir -p /data && chown hermes /data
USER hermes
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"

ENTRYPOINT ["sh", "/app/scripts/docker_entrypoint.sh"]
