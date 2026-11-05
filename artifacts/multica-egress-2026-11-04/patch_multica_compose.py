"""Patch /opt/multica/docker-compose.yml: the agent runtime behind the egress allowlist proxy (2026-11-04)."""
p = "/opt/multica/docker-compose.yml"
s = open(p).read()


def once(old, new):
    global s
    assert s.count(old) == 1, ("anchor", old, s.count(old))
    s = s.replace(old, new)


once("    networks: [db, app]\n", "    networks: [db, app, agent]\n")
once('      MULTICA_DAEMON_AUTO_UPDATE: "false"\n',
     '      MULTICA_DAEMON_AUTO_UPDATE: "false"\n'
     "      # Egress only through the allowlist proxy (2026-11-04): the agent network has no route out.\n"
     "      HTTPS_PROXY: http://egress:8888\n      https_proxy: http://egress:8888\n"
     "      HTTP_PROXY: http://egress:8888\n      http_proxy: http://egress:8888\n"
     "      NO_PROXY: backend,localhost,127.0.0.1\n      no_proxy: backend,localhost,127.0.0.1\n")
once("    networks: [app]\n    mem_limit: 3g\n", "    networks: [agent]\n    mem_limit: 3g\n")
once("    depends_on: [backend]\n    env_file:", "    depends_on: [backend, egress]\n    env_file:")
egress = """
  # Egress allowlist proxy for the agent runtime (2026-11-04): tinyproxy refuses every host not in egress/allow.
  egress:
    image: multica-egress:20261104
    build: { context: ./egress }
    container_name: multica-egress
    networks: [agent, app]
    read_only: true
    tmpfs: ["/tmp", "/run"]
    mem_limit: 128m
    cpus: 0.5
    pids_limit: 128
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    restart: unless-stopped
    logging: *logging
"""
once("\nnetworks:\n  db: { internal: true }\n  app: {}\n",
     egress + "\nnetworks:\n  db: { internal: true }\n  app: {}\n"
     "  agent:\n    internal: true\n    ipam:\n      config: [{ subnet: 10.250.0.0/24 }]\n")
open(p, "w").write(s)
print("patched")
