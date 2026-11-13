"""Inventory source, OS packages and Python distributions without network or service data."""

from hashlib import sha256
from importlib.metadata import distributions
import json
from pathlib import Path
import subprocess


root = Path("/app")
files = [*(root / "aimarket_hub").rglob("*"), *(path for path in root.iterdir() if path.is_file())]
source = {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(files)
          if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
query = "${binary:Package}\t${Version}\t${db:Status-Abbrev}\n"
debian = {}
for row in subprocess.check_output(["dpkg-query", "-W", "-f=" + query], text=True).splitlines():
    name, version, status = row.split("\t")
    if status.startswith("ii"):
        debian[name] = version
print(json.dumps({"source": source, "debian": debian,
                  "python": sorted([dist.metadata["Name"], dist.version] for dist in distributions())}, sort_keys=True))
