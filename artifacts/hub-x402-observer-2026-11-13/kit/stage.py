"""Stage the four x402 files from the reviewed commit and their expected preimages."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys


REVISION = "d6a77ce9f9c2de01738e1264e29a0655e38373b3"
FILES = ("hub_routes/bridge.py", "hub_routes/federation.py", "observed_sellers.py", "x402_bridge.py")
def read_git(repo, revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=repo)


kit = Path(__file__).resolve().parent
repo = kit.parents[2]
output = Path(sys.argv[1]).resolve()
output.mkdir(mode=0o700, parents=True, exist_ok=True)
if any(output.iterdir()):
    raise SystemExit("staging directory must be empty")
old_hashes, new_hashes = [], []
for path in FILES:
    source = "aimarket-hub/aimarket_hub/" + path
    old, new = (read_git(repo, revision, source) for revision in (REVISION + "^", REVISION))
    if new == old:
        raise SystemExit(f"missing change for {path}")
    target = output / "overlay" / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(new)
    old_hashes.append(f"{hashlib.sha256(old).hexdigest()}  {path}\n")
    new_hashes.append(f"{hashlib.sha256(new).hexdigest()}  {path}\n")
(output / "preimage.sha256").write_text("".join(old_hashes))
(output / "overlay.sha256").write_text("".join(new_hashes))
for name in (".dockerignore", "Dockerfile", "deploy.sh", "inventory.py", "smoke.py"):
    shutil.copyfile(kit / name, output / name)
print(f"staged {len(FILES)} x402 files from {REVISION} at {output}")
