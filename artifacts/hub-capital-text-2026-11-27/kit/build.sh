#!/usr/bin/env bash
# build.sh CONTAINER — <running image>-capitaltext-20261127, then check it without the hub's data or settings: the three patched
# modules import, and /openapi.json of an app built on a throw-away SQLite file has no "acex" in any case.
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
RUNUSER="$(docker inspect -f '{{.Config.User}}' "$BASE")"; RUNUSER="${RUNUSER:-root}"
NEW="$BASE-capitaltext-20261127"
docker build -q --build-arg BASE="$BASE" --build-arg RUNUSER="$RUNUSER" -t "$NEW" "$D" >/dev/null
# The image's own environment (empty settings, data paths) belongs to the live hub, so the check runs with PATH and
# PYTHONPATH only, in the image's working directory (/app, where the hub imports from), as root in a throw-away
# container (the apex image carries an old root-owned /app/data/channels.db that the hub user cannot open for writing).
IENV="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NEW" | grep -E '^(PATH|PYTHONPATH)=' | tr '\n' ' ')"
docker run --rm --network none --user 0 --entrypoint env "$NEW" -i $IENV HOME=/tmp AIMARKET_AUTO_CRAWL=0 AIMARKET_FEDERATION_ASSAY=0 python3 -c '
import json, re, tempfile, os
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
d = tempfile.mkdtemp(); c = HubConfig(); c.hub_url = "https://smoke.example"
c.db_path = os.path.join(d, "hub.db"); c.signing_key_path = os.path.join(d, "hub.key")
doc = create_app(config=c, db=HubDatabase(c.db_path), signer=Signer(c.signing_key_path)).openapi()
s = json.dumps(doc)
tags = doc["paths"]["/api/v2/capital/pricing"]["get"]["tags"]
print("openapi acex:", len(re.findall("acex", s, re.I)), "| capital tag:", tags, "| paths:", len(doc["paths"]))
assert not re.search("acex", s, re.I) and tags == ["capital"]
'
echo "$NEW"
