"""Stage the reviewed Hub bridge file against the exact deployed x402 preimage."""

from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys


kit = Path(__file__).resolve().parent
repo = kit.parents[2]
path = "aimarket-hub/aimarket_hub/x402_bridge.py"
old = subprocess.check_output(["git", "show", f"d6a77ce9f:{path}"], cwd=repo)
assert sha256(old).hexdigest() == "cf6114d5561385465faa528bd8c090ffc10347ec352cbccb92a16f0ab8cbf2e3"
new = (repo / path).read_bytes()
assert old != new
output = Path(sys.argv[1]).resolve()
output.mkdir(mode=0o700, parents=True, exist_ok=True)
if any(output.iterdir()):
    raise SystemExit("staging directory must be empty")
(output / "overlay").mkdir()
(output / "overlay" / "x402_bridge.py").write_bytes(new)
(output / "preimage.sha256").write_text(f"{sha256(old).hexdigest()}  x402_bridge.py\n")
(output / "overlay.sha256").write_text(f"{sha256(new).hexdigest()}  x402_bridge.py\n")
for name in (".dockerignore", "Dockerfile", "deploy.sh", "inventory.py", "smoke.py", "live-cmc-receipt.py"):
    shutil.copyfile(kit / name, output / name)
print(f"staged x402_bridge.py at {output}")
