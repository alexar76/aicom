# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Dockerfile
# ============================================================================
# Single-container deployment with all components:
#   - Python 3.12 backend (FastAPI + Uvicorn)
#   - Node.js 20 + Next.js frontend
#   - All data persisted in /app/data
#
# Sandbox Docker support:
#   By default the Docker CLI is NOT bundled — sandbox container preview
#   is disabled (the API gracefully degrades to a static HTTP fallback).
#
#   To opt into Docker-in-Docker sandbox preview, build with:
#     docker build --build-arg INCLUDE_DOCKER_SANDBOX=1 -t aicom .
#
#   ⚠️  DinD requires running the resulting container as `--privileged` or
#       with `/var/run/docker.sock` mounted. Both grant near-root access to
#       the host kernel. Only enable on hardened internal infra.
#       For external preview, prefer a remote Docker host via DOCKER_HOST.
# ============================================================================

FROM ubuntu:24.04 AS base

ARG INCLUDE_DOCKER_SANDBOX=0

LABEL version="2.1.0"
LABEL description="AUTONOMOUS AI-FACTORY — Autonomous AI Company Platform"
LABEL maintainer="AI-Factory Team"

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── System Dependencies ────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python
    python3.12 \
    python3.12-dev \
    python3-pip \
    python3-venv \
    # Node.js
    curl \
    gnupg \
    ca-certificates \
    # Build tools
    build-essential \
    pkg-config \
    libssl-dev \
    libffi-dev \
    # Utilities (minimal runtime; use docker exec for interactive debugging)
    git \
    procps \
    # Monitoring
    prometheus-node-exporter \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Optional Docker-in-Docker (opt-in via --build-arg) ─────────────────────
# Default: NOT installed (smaller image, no privileged-container requirement).
# When INCLUDE_DOCKER_SANDBOX=1, installs docker.io and docker-compose-v2 so
# /api/sandbox/* can spin up real preview containers. Container then needs
# --privileged or socket mount to actually run docker.
RUN if [ "$INCLUDE_DOCKER_SANDBOX" = "1" ]; then \
        echo "Installing Docker CLI for sandbox preview…" && \
        apt-get update && apt-get install -y --no-install-recommends \
            docker.io docker-compose-v2 && \
        apt-get clean && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Skipping Docker CLI install (set --build-arg INCLUDE_DOCKER_SANDBOX=1 to enable)"; \
    fi
ENV AIFACTORY_SANDBOX_DOCKER_AVAILABLE=${INCLUDE_DOCKER_SANDBOX}

# ── Node.js 20 LTS ─────────────────────────────────────────────────────────
# Install via NodeSource apt repo with explicit GPG keyring (no `curl | bash`),
# so a compromised deb.nodesource.com setup script can't RCE the image build.
# npm pinned to a fixed version for reproducible builds.
RUN install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && chmod 0644 /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g npm@10.9.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Application Directory ──────────────────────────────────────────────────
WORKDIR /app

# ── Python Virtual Environment ─────────────────────────────────────────────
RUN python3.12 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# ── Python Dependencies ────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Headless Chromium for QA browser E2E (Playwright)
RUN /app/venv/bin/python -m playwright install chromium \
    && /app/venv/bin/python -m playwright install-deps chromium

# ── Application Code ───────────────────────────────────────────────────────
COPY . .

# ── Frontend Build ─────────────────────────────────────────────────────────
# NEXT_PUBLIC_* is inlined at `next build`; override via compose build args for production domains.
ARG NEXT_PUBLIC_SITE_URL=http://localhost:9080
ARG NEXT_PUBLIC_GA_MEASUREMENT_ID=
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}
ENV NEXT_PUBLIC_GA_MEASUREMENT_ID=${NEXT_PUBLIC_GA_MEASUREMENT_ID}
WORKDIR /app/web/frontend
# PWA manifest requires on-disk PNGs (prebuild); ensure icons exist if npm lifecycle changes.
RUN python3 scripts/gen_pwa_icons.py
# --ignore-scripts blocks malicious postinstall hooks from transitive deps (EXP-89).
# `npm rebuild` after install ensures native modules that legitimately need a
# build step (e.g., sharp) still get compiled, in a controlled phase.
RUN npm ci --ignore-scripts \
    && npm rebuild \
    && npm run build \
    && npm prune --production

# ── Runtime Configuration ──────────────────────────────────────────────────
WORKDIR /app

# Create data directories
# Bind-mount ./data hides image /app/data at runtime — keep LLM template under /app/llm for first-run bootstrap.
RUN mkdir -p /app/data/config /app/data/specs /app/data/arch /app/data/code /app/data/bugs /app/data/state /app/data/logs /app/data/telemetry /app/data/reports/director /app/data/secrets /app/data/sandboxes /app/data/public/pipeline_demo_replay \
    && mkdir -p /app/git-repos \
    && mkdir -p /app/llm/_defaults \
    && cp /app/data/config/model_providers.example.yaml /app/llm/_defaults/model_providers.example.yaml

# ── Non-root runtime user ──────────────────────────────────────────────────
# Drop from root before CMD so a Python/JS RCE doesn't immediately get root
# inside the container (and via docker socket / --privileged: on the host).
# uid 10001 to stay clear of Ubuntu's reserved 1000–9999 range.
RUN groupadd --system --gid 10001 aifactory \
    && useradd --system --uid 10001 --gid aifactory --shell /usr/sbin/nologin --home-dir /app aifactory \
    && chown -R aifactory:aifactory /app

# Set permissions (after chown so ownership sticks)
RUN chmod -R 755 /app \
    && chmod -R 700 /app/data/secrets

USER aifactory:aifactory

# ── Health Check ───────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/api/health')" || exit 1

# ── Entry Point ────────────────────────────────────────────────────────────
EXPOSE 8080

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Start all services via the platform entry point
CMD ["/app/entrypoint.sh"]
