#!/usr/bin/env python3
"""Run on attested as root: python3 -I patch_compose_v2.py

The provider's second design in /opt/multica/docker-compose.yml: the new image, the `db` network (for the
read-only function) instead of `agent` (agents no longer reach the provider at all), and no RESULT_BASE.
Backup next to the file; refuses on a missing anchor."""
import shutil
from pathlib import Path

F = Path("/opt/multica/docker-compose.yml")
text = F.read_text()
if "image: multica-provider:20261104b" in text:
    raise SystemExit("already patched")
pairs = [
    ("    image: multica-provider:20261104\n", "    image: multica-provider:20261104b\n"),
    ("    networks: [app, agent, attested_hub]\n", "    networks: [app, db, attested_hub]\n"),
    ("      RESULT_BASE: http://multica-provider:8090\n", ""),
]
for old, _ in pairs:
    assert text.count(old) == 1, old.strip()
shutil.copy2(F, F.with_name("docker-compose.yml.bak-20261104-provider-v2"))
for old, new in pairs:
    text = text.replace(old, new)
F.write_text(text)
print("multica compose: provider on image 20261104b, networks app, db, attested_hub")
