"""Check the signed trixie-security index and the exact packages entering the image."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import lzma
from pathlib import Path
import subprocess
import sys


PACKAGES = {
    "apt": ("3.0.4", "pool/updates/main/a/apt/apt_3.0.4_amd64.deb"),
    "libapt-pkg7.0": ("3.0.4", "pool/updates/main/a/apt/libapt-pkg7.0_3.0.4_amd64.deb"),
    "zlib1g": ("1:1.3.dfsg+really1.3.1-1+deb13u1",
               "pool/updates/main/z/zlib/zlib1g_1.3.dfsg+really1.3.1-1+deb13u1_amd64.deb"),
}


def paragraphs(text):
    for paragraph in text.split("\n\n"):
        fields = {}
        field = None
        for line in paragraph.splitlines():
            if line.startswith((" ", "\t")):
                if field is None:
                    raise ValueError("continuation without a field")
                fields[field] += "\n" + line.strip()
            elif line:
                field, value = line.split(":", 1)
                if field in fields:
                    raise ValueError(f"duplicate field {field}")
                fields[field] = value.strip()
        if fields:
            yield fields


def check(path, expected_hash, expected_size):
    size = path.stat().st_size
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if (digest, size) != (expected_hash, int(expected_size)):
        raise ValueError(f"checksum or size mismatch for {path.name}")
    return {"file": path.name, "sha256": digest, "bytes": size}


def main():
    bundle, signed_release = map(Path, sys.argv[1:])
    release, = paragraphs(signed_release.read_text())
    now = datetime.now(timezone.utc)
    if release["Origin"] != "Debian" or release["Codename"] != "trixie-security":
        raise ValueError("unexpected Debian archive identity")
    if not parsedate_to_datetime(release["Date"]) <= now < parsedate_to_datetime(release["Valid-Until"]):
        raise ValueError("Debian archive signature date is outside Release validity")
    index_path = "main/binary-amd64/Packages.xz"
    index_hash, index_size, _ = next(line.split() for line in release["SHA256"].splitlines()
                                     if line.split() and line.split()[-1] == index_path)
    checked_index = check(bundle / "Packages.xz", index_hash, index_size)
    with lzma.open(bundle / "Packages.xz", "rt") as stream:
        index = list(paragraphs(stream.read()))
    packages = {}
    for name, (version, path) in PACKAGES.items():
        row, = (row for row in index if row.get("Package") == name and row.get("Version") == version
                and row.get("Architecture") == "amd64")
        if row["Filename"] != path:
            raise ValueError(f"unexpected pool path for {name}")
        artifact = bundle / Path(path).name
        packages[name] = check(artifact, row["SHA256"], row["Size"])
        identity = [subprocess.check_output(["dpkg-deb", "--field", artifact, field], text=True).strip()
                    for field in ("Package", "Version", "Architecture")]
        if identity != [name, version, "amd64"]:
            raise ValueError(f"package identity mismatch for {name}")
        packages[name]["version"] = version
    print(json.dumps({"signed_archive": release["Codename"], "date": release["Date"],
                      "valid_until": release["Valid-Until"], "index": checked_index, "packages": packages},
                     sort_keys=True))


if __name__ == "__main__":
    main()
