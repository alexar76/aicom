"""Fetch QuickJS-ng for WASI, check it against a pinned SHA-256. Used by the Dockerfile.

    python scripts/fetch_qjs_wasi.py /opt/qjs-wasi

The engine for JavaScript handlers (hestia.sandbox): qjs-wasi.wasm from the quickjs-ng release
(MIT, Fabrice Bellard, Charlie Gordon and the quickjs-ng authors). The digest below is the one
GitHub publishes for the asset, checked again here; a mismatch aborts the image build. The
owner approved this download on 2026-11-20.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

VERSION = "0.17.0"
URL = f"https://github.com/quickjs-ng/quickjs/releases/download/v{VERSION}/qjs-wasi.wasm"
SHA256 = "42a732a676ec2d93488c19411e0fad283bf72658fdad746f089914b523c783b1"


def main(target: str) -> None:
    with urllib.request.urlopen(URL, timeout=120) as response:  # noqa: S310 — pinned https URL
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"qjs-wasi digest {digest} != pinned {SHA256}: refusing it")
    if not data.startswith(b"\0asm"):
        raise SystemExit("qjs-wasi.wasm is not a WebAssembly module")
    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)
    (root / "qjs-wasi.wasm").write_bytes(data)
    print(f"QuickJS-ng {VERSION} for WASI at {root} ({len(data)} bytes, sha256 {digest[:12]}…)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/opt/qjs-wasi")
