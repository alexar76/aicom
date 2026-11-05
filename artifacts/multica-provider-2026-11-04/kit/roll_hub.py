#!/usr/bin/env python3
"""Run on attested as root after provider_secrets.py. Sets the three hub variables on the LIVE hub container (its image
stays as it is) with rollout_container.py, which keeps every other setting, rolls back on a failed health check
and reports names only. Values are read here and passed straight through; nothing is printed."""
import json
import subprocess
from pathlib import Path

C = "attested-memory-hub-hub-1"
env_file = {}
for line in Path("/opt/aicom/attested/attested-memory-hub/.env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env_file[k.strip()] = v.strip().strip('"').strip("'")
live = dict(e.split("=", 1) for e in json.loads(subprocess.check_output(["docker", "inspect", C]))[0]["Config"]["Env"])
token = env_file["MULTICA_PROVIDER_PUBLISHER_TOKEN"]


def add(value, item):
    items = [x for x in value.split(",") if x]
    return ",".join(items if any(x.split(":")[0] == item.split(":")[0] for x in items) else items + [item])


sets = {
    "AIMARKET_PUBLISHER_TOKENS": add(live["AIMARKET_PUBLISHER_TOKENS"], f"multica-provider:{token}"),
    "AIMARKET_INVOKE_HOST_GATEWAY": add(live["AIMARKET_INVOKE_HOST_GATEWAY"], "multica-provider"),
    "AIMARKET_SUPPLY_OPERATOR_PUBLISHERS": add(live["AIMARKET_SUPPLY_OPERATOR_PUBLISHERS"], "multica-provider"),
}
cmd = ["python3", "rollout_container.py", C, "--health", "http://127.0.0.1:9084/ai-market/v2/health"]
for k, v in sets.items():
    cmd += ["--set", f"{k}={v}"]
subprocess.run(cmd, cwd="/root/hub-3160-main-20261021", check=True)
