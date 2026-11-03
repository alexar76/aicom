"""Publish only the verified 3.17.0 artifacts. Credentials never enter arguments/output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--token-file", type=Path)
args = parser.parse_args()
token = args.token_file.expanduser().read_text().strip() if args.token_file else os.environ.get("PYPI_API_TOKEN") or os.environ.get("TWINE_PASSWORD")
if not token:
    raise SystemExit("A PyPI project token is required via --token-file or PYPI_API_TOKEN; do not paste it in chat.")
if not token.startswith("pypi-"):
    raise SystemExit("The supplied credential is not a PyPI API token.")

expected = json.loads((ROOT / "artifact-hashes.json").read_text())
assert set(expected) == {"aimarket_hub-3.17.0-py3-none-any.whl", "aimarket_hub-3.17.0.tar.gz"}
for name, metadata in expected.items():
    assert hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest() == metadata["sha256"], name
sources = json.loads((ROOT / "source-manifest.json").read_text())["files"]
for name, digest in sources.items():
    assert hashlib.sha256((WORKSPACE / "aimarket-hub" / name).read_bytes()).hexdigest() == digest, "Source changed: " + name

def published():
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/aimarket-hub/3.17.0/json", timeout=30) as response:
            return json.load(response)["urls"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise

existing = {entry["filename"]: entry for entry in published()}
for name, entry in existing.items():
    assert name in expected and entry["digests"]["sha256"] == expected[name]["sha256"], "Conflicting published artifact: " + name
pending = [ROOT / "dist" / name for name in expected if name not in existing]
if pending:
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict", *map(str, pending)], check=True)
    for archive in pending:
        subprocess.run([str(WORKSPACE / ".venv/bin/python"), "-I", str(WORKSPACE / "scripts/verify_distribution_secrets.py"), str(archive)], check=True)
    env = {**os.environ, "TWINE_USERNAME": "__token__", "TWINE_PASSWORD": token, "TWINE_NON_INTERACTIVE": "1"}
    subprocess.run([sys.executable, "-m", "twine", "upload", "--non-interactive", "--disable-progress-bar", "--repository-url", "https://upload.pypi.org/legacy/", *map(str, pending)], env=env, check=True)
    del env["TWINE_PASSWORD"]
del token
final = {entry["filename"]: entry for entry in published()}
assert set(final) == set(expected)
for name, entry in final.items():
    assert entry["digests"]["sha256"] == expected[name]["sha256"]
(ROOT / "pypi-publication.json").write_text(json.dumps({"project": "aimarket-hub", "version": "3.17.0", "files": final}, indent=2) + "\n")
print("Verified PyPI publication: https://pypi.org/project/aimarket-hub/3.17.0/")
