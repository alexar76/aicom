#!/usr/bin/env python3
"""Build the pipeline client the Hub serves at /clients/, from this tree.

    aimarket-hub/.venv/bin/python scripts/build_pipeline_client.py                  # Python >= 3.11
    aimarket-hub/.venv/bin/python scripts/build_pipeline_client.py --check-served https://modelmarket.dev

Writes the wheel, release.json {filename, version, sha256, commit} and the five guides
(render_pipeline_client_guides.py). static/client is a deployment artifact, not committed.

/clients/<wheel> is served `immutable`, so one version must mean one set of bytes forever. The
wheel is built reproducibly (SOURCE_DATE_EPOCH = the HEAD commit time), and --check-served refuses
to produce a release whose version a hub already serves with different bytes: bump the version.
Before this script the served 3.14.0 wheel no longer matched the 3.14.0 code in the tree, and
nothing could tell.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "aimarket-hub"
OUT = HUB / "aimarket_hub" / "static" / "client"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-served", metavar="HUB_URL", help="refuse if this hub serves the same version with other bytes")
    args = ap.parse_args()
    if subprocess.run(["git", "status", "--porcelain", "--", "aimarket-hub/aimarket_hub", "aimarket-hub/pyproject.toml"],
                      cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip():
        sys.exit("aimarket-hub has uncommitted changes: a served wheel must be a commit")
    version = tomllib.loads((HUB / "pyproject.toml").read_text())["project"]["version"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    epoch = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["uv", "build", "--wheel", "--out-dir", tmp, str(HUB)], check=True,
                       env={**os.environ, "SOURCE_DATE_EPOCH": epoch}, stdout=subprocess.DEVNULL)
        wheels = list(Path(tmp).glob(f"aimarket_hub-{version}-py3-none-any.whl"))
        if len(wheels) != 1:
            sys.exit(f"expected one aimarket_hub-{version} wheel, got {[w.name for w in Path(tmp).iterdir()]}")
        wheel = wheels[0]
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if args.check_served:
            try:
                with urllib.request.urlopen(args.check_served.rstrip("/") + "/clients/pipeline.json", timeout=15) as r:
                    served = json.load(r)
            except Exception as exc:  # noqa: BLE001 - nothing served yet is fine
                served = None
                print(f"no served release to compare ({exc})")
            if served and served.get("filename") == wheel.name and served.get("sha256") != digest:
                sys.exit(f"{args.check_served} serves {wheel.name} with sha256 {served.get('sha256')}, this build is "
                         f"{digest}: the URL is cached as immutable, so bump the version instead of replacing it")
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("aimarket_hub-*.whl"):
            old.unlink()
        shutil.copy2(wheel, OUT / wheel.name)
    (OUT / "release.json").write_text(json.dumps(
        {"filename": wheel.name, "version": version, "sha256": digest, "commit": commit}, indent=2) + "\n")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_pipeline_client_guides.py"), str(OUT)], check=True)
    print(f"{wheel.name}  sha256 {digest}  commit {commit[:12]}  -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
