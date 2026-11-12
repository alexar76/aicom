# Resolve and record the base digest and installed tinyproxy package version for rollout.
FROM ubuntu:24.04
RUN apt-get update \
    && apt-get install -y --no-install-recommends tinyproxy ca-certificates \
    && dpkg-query -W tinyproxy > /tinyproxy-package-version.txt \
    && rm -rf /var/lib/apt/lists/*
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
USER 65534:65534
ENTRYPOINT ["/usr/bin/tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
