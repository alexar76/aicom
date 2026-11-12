#!/usr/bin/env python3
"""Apply the reviewed local Multica result patch only to known source bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path: Path) -> str | None:
    if path.is_symlink():
        raise ValueError("refusing a symlink in a patched source path")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def apply(source: Path, check_only: bool) -> str:
    bundle = Path(__file__).resolve().parent / "patches"
    manifest = json.loads((bundle / "0001-redact-task-results.json").read_text())
    patch = bundle / "0001-redact-task-results.patch"
    if digest(patch) != manifest["patch_sha256"]:
        raise ValueError("patch checksum mismatch")
    source = source.resolve(strict=True)
    before, after = True, True
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe manifest path")
        path = source / relative
        if not path.resolve().is_relative_to(source):
            raise ValueError("source path escapes the checkout")
        actual = digest(path)
        before &= actual == entry["before_sha256"]
        after &= actual == entry["after_sha256"]
    if after:
        return "already applied; all patched file checksums match"
    if not before:
        raise ValueError("source differs from reviewed v0.8.0 files; no changes made")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True, capture_output=True)
    if check_only:
        return "compatible; all original source checksums match; no changes made"
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True, capture_output=True)
    for entry in manifest["files"]:
        if digest(source / entry["path"]) != entry["after_sha256"]:
            raise ValueError("post-apply checksum mismatch; inspect the local checkout")
    return "applied locally; all patched file checksums match"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true", help="validate without writing source files")
    args = parser.parse_args()
    try:
        print(apply(args.source_root, args.check))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Never echo source contents, command stderr or an agent's output here.
        print(f"output patch refused: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
