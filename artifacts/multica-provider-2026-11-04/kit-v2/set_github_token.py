#!/usr/bin/env python3
"""For the owner. Run on attested as root:  ssh -t attested 'python3 -I /root/multica-provider-20261104/set_github_token.py'

Asks for the GitHub token without echoing it, writes GITHUB_TOKEN into /opt/multica/secrets/provider.env (0600,
backup first) and re-creates the provider so it reads GitHub with that token. Then it asks GitHub how many
requests the token has left (that call is free) and prints only the numbers.

The token must have NO scopes (classic token with every box unchecked, or a fine-grained token with "Public
repositories (read-only)" and no permissions): it is only for reading public data at 5,000 requests an hour."""
import getpass
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

ENV = Path("/opt/multica/secrets/provider.env")
token = getpass.getpass("GitHub token (not shown): ").strip()
if not token or any(c.isspace() for c in token):
    raise SystemExit("empty or malformed token, nothing changed")
request = urllib.request.Request("https://api.github.com/rate_limit", headers={
    "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "aicom-multica-provider"})
with urllib.request.urlopen(request, timeout=10) as response:
    core = json.load(response)["resources"]["core"]
    scopes = response.headers.get("X-OAuth-Scopes")
if scopes:
    raise SystemExit(f"this token has scopes ({scopes}); make one with none. Nothing changed.")
print(f"GitHub accepts the token: limit {core['limit']}, remaining {core['remaining']}")
lines = [l for l in ENV.read_text().splitlines() if not l.startswith("GITHUB_TOKEN=")]
shutil.copy2(ENV, ENV.with_name("provider.env.bak-github-token"))
fd = os.open(ENV, os.O_WRONLY | os.O_TRUNC)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines + [f"GITHUB_TOKEN={token}"]) + "\n")
os.chmod(ENV, 0o600)
print("written name: GITHUB_TOKEN ->", ENV)
# Only the second design reads GitHub itself; never start the first one (paused 2026-11-04) by accident.
if "image: multica-provider:20261104b" not in Path("/opt/multica/docker-compose.yml").read_text():
    raise SystemExit("the provider's second design is not rolled yet: token saved, provider NOT started")
subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "provider"], cwd="/opt/multica", check=True)
print("provider re-created with GITHUB_TOKEN; check: docker exec multica-provider python -c "
      "\"import urllib.request,json;print(json.load(urllib.request.urlopen('http://127.0.0.1:8090/healthz')))\"")
