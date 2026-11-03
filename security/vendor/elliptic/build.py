#!/usr/bin/env python3
"""Reproduce the private elliptic backport from integrity-pinned upstream bytes."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
VERSION = "6.6.1+aicom.1"
ARCHIVE = HERE / "elliptic-6.6.1-aicom.1.tgz"
UPSTREAM_INTEGRITY = "RaddvvMatK2LJHqFJ+YA4WysVN5Ita9E35botqIYspQ4TkRAlCicdzKOjlyv/1Za5RyTNn7di//eEV0uTAfe3g=="


def build():
    upstream = (HERE / "upstream-6.6.1.tgz").read_bytes()
    assert base64.b64encode(hashlib.sha512(upstream).digest()).decode() == UPSTREAM_INTEGRITY
    with tarfile.open(fileobj=io.BytesIO(upstream)) as archive:
        files = {}
        for entry in archive.getmembers():
            assert entry.isfile() and entry.name.startswith("package/")
            assert ".." not in Path(entry.name).parts
            files[entry.name] = archive.extractfile(entry).read()
    name = "package/lib/elliptic/ec/index.js"
    with tempfile.TemporaryDirectory(prefix="elliptic-backport-") as temp:
        target = Path(temp) / "lib/elliptic/ec/index.js"
        target.parent.mkdir(parents=True)
        target.write_bytes(files[name])
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i",
                        str(HERE / "CVE-2025-14505.patch")], cwd=temp, check=True,
                       stdout=subprocess.PIPE)
        patched = target.read_bytes()
    assert patched != files[name]
    files[name] = patched
    metadata = json.loads(files["package/package.json"])
    assert metadata["name"] == "elliptic" and metadata["version"] == "6.6.1"
    metadata.update(version=VERSION, private=True)
    files["package/package.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            for path, data in sorted(files.items()):
                entry = tarfile.TarInfo(path)
                entry.size, entry.mode = len(data), 0o644
                archive.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-installed", action="store_true")
    args = parser.parse_args()
    data = build()
    if args.check or args.check_installed:
        assert ARCHIVE.read_bytes() == data, "Rebuild the committed backport archive"
    else:
        ARCHIVE.write_bytes(data)
    if args.check_installed:
        project = HERE.parents[2] / "contracts/evm/lib/openzeppelin-contracts"
        installed = project / "node_modules/elliptic"
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for entry in archive.getmembers():
                target = installed / entry.name.removeprefix("package/")
                assert target.read_bytes() == archive.extractfile(entry).read(), str(target)
        lock = json.loads((project / "package-lock.json").read_text())
        entries = [entry for path, entry in lock["packages"].items()
                   if path.endswith("node_modules/elliptic")]
        assert len(entries) == 1 and entries[0]["version"] == VERSION
        assert entries[0]["integrity"] == "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    print(json.dumps({"version": VERSION, "archive": ARCHIVE.name,
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "integrity": "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()}))


if __name__ == "__main__":
    main()
