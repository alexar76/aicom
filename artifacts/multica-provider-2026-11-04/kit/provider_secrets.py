#!/usr/bin/env python3
"""Run on attested as root. Creates the provider's secrets without printing any value.

- a publisher token for the attested hub (MULTICA_PROVIDER_PUBLISHER_TOKEN in the hub's .env, backup first);
- /opt/multica/secrets/provider.env (0600): the hub's internal capability token, that publisher token and the
  Multica autopilot webhook URL (backend address + the path saved privately in webhook.path).
"""
import os
import secrets
import shutil
from pathlib import Path

HUB_ENV = Path("/opt/aicom/attested/attested-memory-hub/.env")
OUT = Path("/opt/multica/secrets/provider.env")
WEBHOOK_PATH = Path(__file__).resolve().parent / "webhook.path"


def read_env(path):
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


env = read_env(HUB_ENV)
capability = env["AIMARKET_CAPABILITY_TOKEN"]
assert len(capability) >= 32
publisher = env.get("MULTICA_PROVIDER_PUBLISHER_TOKEN")
if not publisher:
    shutil.copy2(HUB_ENV, HUB_ENV.with_name(".env.bak-20261104-provider"))
    publisher = secrets.token_urlsafe(32)
    with HUB_ENV.open("a") as f:
        f.write(f"\n# Multica provider publisher token (2026-11-04)\nMULTICA_PROVIDER_PUBLISHER_TOKEN={publisher}\n")
path = WEBHOOK_PATH.read_text().strip()
assert path.startswith("/api/webhooks/autopilots/")
OUT.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(f"AIMARKET_CAPABILITY_TOKEN={capability}\nAIMARKET_PUBLISHER_TOKEN={publisher}\n"
            f"MULTICA_WEBHOOK_URL=http://multica-backend-1:8080{path}\n")
print("written names:", "AIMARKET_CAPABILITY_TOKEN AIMARKET_PUBLISHER_TOKEN MULTICA_WEBHOOK_URL ->", OUT,
      "| hub .env has MULTICA_PROVIDER_PUBLISHER_TOKEN")
