# Egress allowlist for the agent runtime (multica/manual §3). The daemon sits on an internal network and reaches
# the internet only through this proxy; tinyproxy refuses every host not in ./allow (FilterDefaultDeny).
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends tinyproxy ca-certificates \
 && rm -rf /var/lib/apt/lists/* && tinyproxy -v
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY allow /etc/tinyproxy/allow
USER nobody
EXPOSE 8888
ENTRYPOINT ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
