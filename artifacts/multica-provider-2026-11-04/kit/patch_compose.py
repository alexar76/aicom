#!/usr/bin/env python3
"""Run on attested as root. Adds the provider service to Multica's compose and the provider to the attested
hub's publisher, gateway and operator-publisher lists. Backups next to each file; refuses on a missing anchor."""
import shutil
from pathlib import Path

MULTICA = Path("/opt/multica/docker-compose.yml")
HUB = Path("/opt/aicom/attested/attested-memory-hub/docker-compose.yml")

SERVICE = """
  # Sells long agent jobs on the attested hub (2026-11-04): a paid order makes a Multica task through the
  # autopilot webhook; the agent hands the digest back over the agent network; the buyer reads it for free.
  provider:
    image: multica-provider:20261104
    container_name: multica-provider
    env_file:
      - path: ./secrets/provider.env
        required: true
    environment:
      AIMARKET_HUB_URL: http://hub:9083
      AIMARKET_INVOKE_BASE: http://multica-provider:8090
      AIMARKET_PUBLISHER_ID: multica-provider
      RESULT_BASE: http://multica-provider:8090
      PROVIDER_DB: /data/jobs.sqlite3
      PROVIDER_SIGNING_KEY_FILE: /data/provider-signing-key.pem
    volumes:
      - provider_data:/data
    networks: [app, agent, attested_hub]
    mem_limit: 256m
    cpus: 0.5
    pids_limit: 128
    read_only: true
    tmpfs: [/tmp]
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    restart: unless-stopped
    logging: *logging
"""

text = MULTICA.read_text()
if "container_name: multica-provider" not in text:
    shutil.copy2(MULTICA, MULTICA.with_name("docker-compose.yml.bak-20261104-provider"))
    anchor = "\n  # Egress allowlist proxy for the agent runtime"
    assert text.count(anchor) == 1, "multica anchor"
    text = text.replace(anchor, SERVICE + anchor)
    assert "\nnetworks:\n" in text and "\nvolumes:\n" in text, "top-level sections"
    text = text.replace("\nnetworks:\n", "\nnetworks:\n  attested_hub:\n    external: true\n    name: attested-memory-hub_default\n", 1)
    text = text.replace("\nvolumes:\n", "\nvolumes:\n  provider_data:\n", 1)
    MULTICA.write_text(text)
    print("multica compose: provider service added")

hub = HUB.read_text()
if "multica-provider" not in hub:
    shutil.copy2(HUB, HUB.with_name("docker-compose.yml.bak-20261104-provider"))
    pairs = [
        ("attested-prove:${ATTESTED_PROVE_PUBLISHER_TOKEN:?run ./start.sh}\n",
         "attested-prove:${ATTESTED_PROVE_PUBLISHER_TOKEN:?run ./start.sh},multica-provider:${MULTICA_PROVIDER_PUBLISHER_TOKEN:?run provider_secrets.py}\n"),
        ("AIMARKET_INVOKE_HOST_GATEWAY: memory-market,truth-layer,provenance-ledger\n",
         "AIMARKET_INVOKE_HOST_GATEWAY: memory-market,truth-layer,provenance-ledger,multica-provider\n"),
        ("AIMARKET_SUPPLY_OPERATOR_PUBLISHERS: memory-market,truth-layer,provenance-ledger,attested-deal,attested-meter,attested-prove\n",
         "AIMARKET_SUPPLY_OPERATOR_PUBLISHERS: memory-market,truth-layer,provenance-ledger,attested-deal,attested-meter,attested-prove,multica-provider\n"),
    ]
    for old, new in pairs:
        assert hub.count(old) == 1, old[:40]
        hub = hub.replace(old, new)
    HUB.write_text(hub)
    print("hub compose: multica-provider added to publishers, gateway hosts, operator publishers")
