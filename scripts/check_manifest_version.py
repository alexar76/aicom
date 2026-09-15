#!/usr/bin/env python3
"""Does a server.json declare the version that is actually published?

The MCP registry lists whatever a manifest says. If the manifest is behind its own
artifact, the listing points at a release that is no longer what `pip install` gives you —
and nothing anywhere reports the drift, because both halves are individually valid.

Measured 2026-08-16: aimarket-oracle-gateway declared 0.2.0 against PyPI 0.3.0,
aimarket-mcp-packager 2.0.1 against 2.1.0, and @alexar76/argus3 0.2.5 against 0.3.0 — three
of five manifests, all quietly stale.

Exits 0 and prints a short note when the manifest is publishable; exits 1 with the
mismatch otherwise. A remotes-only manifest has no artifact to drift from.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 15.0


def published_version(registry: str, identifier: str) -> str | None:
    """The version that registry currently serves, or None if it cannot be determined.

    None is not a failure: an unreachable index must not block a publish the operator
    asked for. The check exists to catch drift, not to gate on network weather.
    """
    urls = {
        "pypi": f"https://pypi.org/pypi/{identifier}/json",
        "npm": f"https://registry.npmjs.org/{identifier}/latest",
    }
    url = urls.get(registry)
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return None
    if registry == "pypi":
        return (payload.get("info") or {}).get("version")
    return payload.get("version")


def check(path: str) -> tuple[bool, str]:
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    packages = manifest.get("packages") or []
    if not packages:
        return True, "(remotes-only, no artifact to match)"

    notes, drifted = [], []
    for package in packages:
        registry = str(package.get("registryType") or "")
        identifier = str(package.get("identifier") or "")
        declared = str(package.get("version") or "")
        live = published_version(registry, identifier)
        if live is None:
            notes.append(f"{identifier}: could not reach {registry or 'registry'}, not checked")
        elif live != declared:
            drifted.append(f"{identifier} declares {declared} but {registry} serves {live}")
        else:
            notes.append(f"{identifier} {declared} matches {registry}")
    if drifted:
        return False, "; ".join(drifted)
    return True, "(" + "; ".join(notes) + ")"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_manifest_version.py <server.json>", file=sys.stderr)
        return 2
    ok, message = check(argv[1])
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
