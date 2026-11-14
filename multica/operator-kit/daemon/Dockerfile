# The Multica daemon in a container, as our own installation runs it (multica/manual §2): the Multica CLI
# from its official release, checksum-verified, and OpenCode, at the versions onboard.sh pins.
FROM node:22.23.4-bookworm-slim
ARG MULTICA_VERSION
ARG OPENCODE_VERSION
ARG TARGETARCH

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git jq python3 ripgrep tini \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; arch="${TARGETARCH:-amd64}"; f="multica-cli-${MULTICA_VERSION}-linux-${arch}.tar.gz"; \
    base="https://github.com/multica-ai/multica/releases/download/v${MULTICA_VERSION}"; \
    cd /tmp; c="curl -fsSLO --retry 10 --retry-delay 6 --retry-all-errors"; $c "$base/$f"; $c "$base/checksums.txt"; \
    grep " ${f}\$" checksums.txt | sha256sum -c -; \
    mkdir x; tar -xzf "$f" -C x; install -m 0755 "$(find x -type f -name multica | head -1)" /usr/local/bin/multica; \
    rm -rf /tmp/*; multica version

RUN npm install -g "opencode-ai@${OPENCODE_VERSION}" && npm cache clean --force && opencode --version

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

USER node
WORKDIR /home/node
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
