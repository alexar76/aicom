# A disposable home for OKX's A2A daemon. OKX will not publish an ASP until `okx-a2a doctor`
# sees an AI runtime bound to it, and the daemon runs that runtime on messages arriving from the
# OKX network — by default with `--permission-mode bypassPermissions`. So it lives here, not on
# anyone's workstation: no host mounts, no docker socket, no secrets, not root. Claude Code is
# installed so the runtime is detected, and it is never logged in, so the daemon cannot run it.
FROM node:22-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git procps \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash okx
USER okx
WORKDIR /home/okx
ENV NPM_CONFIG_PREFIX=/home/okx/.npm-global \
    PATH=/home/okx/.npm-global/bin:/home/okx/.local/bin:/usr/local/bin:/usr/bin:/bin
RUN npm install -g --no-audit --no-fund @anthropic-ai/claude-code && npm cache clean --force
COPY --chown=okx:okx entrypoint.sh /usr/local/bin/okx-sandbox-entrypoint
ENTRYPOINT ["/usr/local/bin/okx-sandbox-entrypoint"]
