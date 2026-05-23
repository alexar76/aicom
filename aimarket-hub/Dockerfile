FROM python:3.12-slim

LABEL org.opencontainers.image.title="modelmarket Hub"
LABEL org.opencontainers.image.description="Federation hub for AI capability discovery and routing"
LABEL org.opencontainers.image.version="3.0.0"
LABEL org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build from repository root:
#   docker build -f aimarket-hub/Dockerfile -t modelmarket-hub .

# ── Core hub ──────────────────────────────────────────────────
COPY aimarket-hub/pyproject.toml ./pyproject.toml
COPY aimarket-hub/aimarket_hub/ ./aimarket_hub/
COPY aimarket-hub/plugins-demo.html /app/plugins-demo.html
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir uvicorn

# ── Protocol schemas (for JSON Schema validation) ─────────────
COPY aimarket-protocol/schemas/ /app/aimarket-protocol/schemas/

# ── Widget static files (served by hub at /widget/) ───────────
COPY aimarket-widget/ /app/aimarket-widget/

# ── All 14 plugins ────────────────────────────────────────────
COPY plugins/ /tmp/plugins/
RUN for d in /tmp/plugins/*/; do pip install --no-cache-dir "$d" 2>/dev/null || true; done \
    && rm -rf /tmp/plugins

# ── Data dir ──────────────────────────────────────────────────
RUN mkdir -p /app/data

ENV AIMARKET_DB_PATH=/app/data/hub.db
ENV AIMARKET_SIGNING_KEY_PATH=/app/data/hub_signing_key
ENV AIMARKET_HUB_URL=http://0.0.0.0:9080
ENV AIMARKET_CRAWL_INTERVAL_S=3600

EXPOSE 9080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9080/.well-known/ai-market.json || exit 1

ENTRYPOINT ["python", "-m", "aimarket_hub", "serve"]
