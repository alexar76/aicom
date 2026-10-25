#!/usr/bin/env python3
"""Reproduce/check the four minimal Solana codec patches (Python 3.11+).

Only reads public crate archives, preferring Cargo's local cache. No registry
source directory, Git state, credentials or audit configuration is modified.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "security/vendor-rust"
CRATES = [
    ("anchor-lang", "1.2.1", "19d595e09daa737c57e9a0ab807e5c0b9278e5aefc463063438768ece09f614b"),
    ("solana-instruction", "4.0.0", "1ea8442b67a58dd54d5497bfc6cd3106b00f9fe6f6877d33c271c3ec4672eedc"),
    ("solana-sysvar", "3.1.1", "6690d3dd88f15c21edff68eb391ef8800df7a1f5cec84ee3e8d1abf05affdf74"),
    ("solana-zk-sdk", "4.0.0", "9602bcb1f7af15caef92b91132ec2347e1c51a72ecdbefdaefa3eac4b8711475"),
]
OMIT = {"Cargo.lock", "Cargo.toml.orig", ".cargo-ok"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(name, version, checksum, offline):
    filename = f"{name}-{version}.crate"
    cache = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "registry/cache"
    cached = sorted(cache.glob(f"*/{filename}"))
    if cached:
        data = cached[0].read_bytes()
    elif offline:
        raise SystemExit(f"Missing cached {filename}; rerun without --offline to GET the public archive")
    else:
        url = f"https://static.crates.io/crates/{name}/{filename}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    if sha(data) != checksum:
        raise SystemExit(f"Archive checksum mismatch: {filename}")
    return data


def patched_files(data, name, version):
    files, changes, vcs = {}, [], None
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as source:
        for entry in source.getmembers():
            path = PurePosixPath(entry.name)
            if path.parts[0] != f"{name}-{version}" or ".." in path.parts or path.is_absolute():
                raise SystemExit(f"Unsafe archive path: {entry.name}")
            if entry.isdir():
                continue
            if not entry.isfile():
                raise SystemExit(f"Non-regular archive member: {entry.name}")
            relative = str(PurePosixPath(*path.parts[1:]))
            if relative in OMIT:
                continue
            original = source.extractfile(entry).read()
            result = original
            if relative == ".cargo_vcs_info.json":
                vcs = json.loads(original)
            if relative == "Cargo.toml":
                text = original.decode()
                text, count = re.subn(
                    r'(\[(?:dependencies|target\.[^\n]+\.dependencies)\.)bincode\]\nversion = "[^"]+"',
                    r'\1aimarket-legacy-wire]\nversion = "=0.1.0"\npath = "../../solana-wire"', text)
                if count != 1:
                    raise SystemExit(f"Expected exactly one codec dependency in {name}, got {count}")
                text = text.replace('"dep:bincode"', '"dep:aimarket-legacy-wire"')
                result = text.encode()
            elif relative.endswith(".rs"):
                result = original.replace(b"bincode::", b"aimarket_legacy_wire::")
            if result != original:
                changes.append({"path": relative, "upstream_sha256": sha(original), "patched_sha256": sha(result)})
            files[relative] = result
    return files, changes, vcs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without changing files")
    parser.add_argument("--offline", action="store_true", help="require cached upstream archives")
    args = parser.parse_args()
    metadata = []
    for name, version, checksum in CRATES:
        files, changes, vcs = patched_files(archive(name, version, checksum, args.offline), name, version)
        folder = DEST / name
        if args.check:
            actual = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            if actual != files:
                differences = sorted(k for k in actual.keys() | files.keys() if actual.get(k) != files.get(k))
                raise SystemExit(f"Unexpected vendor differences in {name}: {differences}")
        else:
            if folder.exists():
                raise SystemExit(f"Refusing to overwrite {folder}; use --check or remove only this generated directory")
            for relative, content in files.items():
                path = folder / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        metadata.append({"crate": name, "version": version, "archive_sha256": checksum,
                         "source": f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
                         "vcs": vcs, "omitted": sorted(OMIT), "changes": changes})
        print(f"Verified {name} {version}: {len(files)} files, {len(changes)} minimal codec patches")
    encoded = (json.dumps(metadata, indent=2) + "\n").encode()
    provenance = DEST / "UPSTREAM.json"
    if args.check:
        if provenance.read_bytes() != encoded:
            raise SystemExit("UPSTREAM.json does not match pinned archive provenance")
    else:
        provenance.write_bytes(encoded)


if __name__ == "__main__":
    main()
