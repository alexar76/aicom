"""Stage the two reviewed hub files (outside records, spec §2.7) over their exact deployed preimages.

Usage: python3 kit/stage.py <empty-directory>
The preimages are the files running in modelmarket-hub on 2026-11-14 (image 60b41cad9c31), which
are byte-identical to local main 4a16d654b; deploy.sh re-checks them in the live container.
"""

from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys


kit = Path(__file__).resolve().parent
repo = kit.parents[2]
source = repo / "aimarket-hub"
output = Path(sys.argv[1]).resolve()
output.mkdir(mode=0o700, parents=True, exist_ok=True)
if any(output.iterdir()):
    raise SystemExit("staging directory must be empty")

deployed_revision = "4a16d654b2b8f55d7cd19f968b0a41ea3e45932d"
preimages = {
    "aimarket_hub/observed_sellers.py": "ad2d1299e395d8e226970b3b8950507dd05f0a3ae4e5ca00e2ddf28d1df71aee",
    "aimarket_hub/hub_routes/federation.py": "ff3a16dcbedda14af44802071b79b30fa780b962feb0a4d8fafc41b0878a71eb",
}
hashes = {}
for name, digest in preimages.items():
    old = subprocess.check_output(["git", "show", f"{deployed_revision}:aimarket-hub/{name}"], cwd=repo)
    assert sha256(old).hexdigest() == digest, name
    data = (source / name).read_bytes()
    hashes[name] = sha256(data).hexdigest()
    assert hashes[name] != digest, f"no change for {name}"
    path = output / "overlay" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

for file, checksums in (("preimage.sha256", preimages), ("overlay.sha256", hashes)):
    (output / file).write_text("".join(f"{digest}  {name}\n" for name, digest in checksums.items()))
(output / "additions.txt").write_text("")
for name in (".dockerignore", "Dockerfile", "deploy.sh", "inventory.py", "smoke.py"):
    shutil.copyfile(kit / name, output / name)
print(f"staged {len(hashes)} reviewed source files at {output}")
