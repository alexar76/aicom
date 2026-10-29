#!/usr/bin/env python3
"""Collect bounded read-only deployment evidence, then verify immutable identities and MOMUS."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
HOST = "histor.modelmarket.dev"
MAX_BYTES = 128 * 1024


def fetch(path):
    request = Request("https://" + HOST + path, headers={
        "User-Agent": "aicom-deployment-acceptance/1", "Cache-Control": "no-cache", "Pragma": "no-cache",
    })
    with urlopen(request, timeout=30) as response:
        target = urlparse(response.url)
        if target.scheme != "https" or target.hostname != HOST:
            raise ValueError("unexpected HTTPS redirect")
        body = response.read(MAX_BYTES + 1)
        status = response.status
    if len(body) > MAX_BYTES:
        raise ValueError("oversized public response")
    return status, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--before-remote", type=Path, default=HERE / "before-remote.json")
    parser.add_argument("--before-head", type=Path, default=HERE / "before-head.json")
    parser.add_argument("--require-stored-issuer", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image) or not re.fullmatch(r"[0-9a-f]{40}", args.source):
        parser.error("immutable image and 40-hex source required")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "admin-vps", "python3", "-"],
        input=(HERE / "collect-remote.py").read_text(), capture_output=True, text=True, timeout=180, check=False,
    )
    if result.returncode or len(result.stdout.encode()) > 1024 * 1024:
        raise RuntimeError("read-only remote collection failed")
    remote = json.loads(result.stdout)
    (args.out_dir / "remote.json").write_text(json.dumps(remote, indent=2) + "\n")
    public = {}
    for name, path, fields in (
        ("health", "/health", ("ok", "service", "version", "profile", "store", "tree_size", "crawl_running")),
        ("issuer", "/api/v1/issuer", ("warden", "patternSet", "recordSet")),
    ):
        status, body = fetch(path)
        raw = json.loads(body)
        public[name] = {"httpStatus": status, **{key: raw.get(key) for key in fields}}
        if name == "health":
            public[name]["historicalInterruptedRunMarker"] = str(raw.get("last_crawl_error") or "").startswith("interrupted")
    # The existing public auditor verifies signature, unchanged issuer, and a
    # consistency proof when the tree grew. It writes only this local witness.
    sys.path.insert(0, str(HERE.parents[3] / "histor"))
    from histor.audit import audit

    witness = args.out_dir / "after-head.json"
    shutil.copyfile(args.before_head, witness)
    public["logAudit"] = audit("https://" + HOST, state=witness)
    (args.out_dir / "public-http.json").write_text(json.dumps(public, indent=2) + "\n")
    for name, path in (
        ("candidate-signed.json", "/security-quality/candidate.json"),
        ("live-signed.json", "/security-quality/latest.json"),
    ):
        status, body = fetch(path)
        if status != 200:
            raise ValueError("quality endpoint unavailable")
        json.loads(body)
        (args.out_dir / name).write_bytes(body)
    verification = subprocess.run([
        "node", str(HERE / "check-acceptance.mjs"),
        "--before", str(args.before_remote),
        "--remote", str(args.out_dir / "remote.json"), "--http", str(args.out_dir / "public-http.json"),
        "--candidate", str(args.out_dir / "candidate-signed.json"), "--live", str(args.out_dir / "live-signed.json"),
        "--image", args.image, "--source", args.source, "--output", str(args.out_dir / "acceptance.json"),
        "--require-stored-issuer", str(args.require_stored_issuer).lower(),
    ], check=False)
    return verification.returncode


if __name__ == "__main__":
    raise SystemExit(main())
