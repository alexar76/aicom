"""Stage the reviewed directory source using exact deployed preimages."""

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

deployed_revision = "a8134bd678c1c47aa491b3c00c390623fcaec0d4"
preimages = {
    "terminal-home.html": "71e51a5b1ac3b88e7012b4b82b657167682d44ce9fb47fa50d18f71273220346",
    "hub-ui-i18n.json": "a478a613708e7f47046aed2e654a523384486ea534ae9c6b42aea33ca8cfbf1d",
    "aimarket_hub/hub_routes/catalog.py": "8610e8f457599b522c9c0aaaf7131a0a59fa7b4d22ab0f83b76e5d37c3580210",
}
additions = ("aimarket_hub/external_services.py",)
hashes = {}
for name in (*preimages, *additions):
    if name in preimages:
        old = subprocess.check_output(["git", "show", f"{deployed_revision}:aimarket-hub/{name}"], cwd=repo)
        assert sha256(old).hexdigest() == preimages[name], name
    data = (source / name).read_bytes()
    hashes[name] = sha256(data).hexdigest()
    assert hashes[name] != preimages.get(name), f"no change for {name}"
    path = output / "overlay" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

for file, checksums in (("preimage.sha256", preimages), ("overlay.sha256", hashes)):
    (output / file).write_text("".join(f"{digest}  {name}\n" for name, digest in checksums.items()))
(output / "additions.txt").write_text("\n".join(additions) + "\n")
for name in (".dockerignore", "Dockerfile", "deploy.sh", "inventory.py", "smoke.py", "custody-readonly.py"):
    shutil.copyfile(kit / name, output / name)
print(f"staged {len(hashes)} reviewed source files at {output}")
