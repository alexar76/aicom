"""Read-only comparison of the frozen and observed public HISTOR 0.5.0 wheels."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import zipfile
from email.parser import BytesParser
from pathlib import Path

DIST_INFO = "aimarket_histor-0.5.0.dist-info/"


def records_valid(archive: zipfile.ZipFile) -> bool:
    records = list(csv.reader(io.StringIO(archive.read(DIST_INFO + "RECORD").decode())))
    assert {row[0] for row in records} == set(archive.namelist())
    for name, digest, size in records:
        if name == DIST_INFO + "RECORD":
            assert not digest and not size
            continue
        body = archive.read(name)
        expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip("=")
        assert digest == expected and size == str(len(body)), name
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-wheel", required=True, type=Path)
    parser.add_argument("--public-wheel", required=True, type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.local_wheel) as local, zipfile.ZipFile(args.public_wheel) as public:
        names = local.namelist()
        assert names == public.namelist() and len(names) == 53
        differences = sorted(name for name in names if local.read(name) != public.read(name))
        assert differences == [DIST_INFO + "RECORD", DIST_INFO + "WHEEL"]
        local_meta = BytesParser().parsebytes(local.read(DIST_INFO + "WHEEL"))
        public_meta = BytesParser().parsebytes(public.read(DIST_INFO + "WHEEL"))
        assert local_meta["Generator"] == "hatchling 1.32.4"
        assert public_meta["Generator"] == "hatchling 1.27.0"
        assert {key: value for key, value in local_meta.items() if key != "Generator"} == {
            key: value for key, value in public_meta.items() if key != "Generator"
        }
        for name in names:
            a, b = local.getinfo(name), public.getinfo(name)
            for field in ("date_time", "compress_type", "compress_size", "file_size", "extra", "comment",
                          "create_system", "create_version", "extract_version", "external_attr", "flag_bits"):
                assert getattr(a, field) == getattr(b, field), (name, field)
        assert local.comment == public.comment
        result = {
            "localSha256": hashlib.sha256(args.local_wheel.read_bytes()).hexdigest(),
            "publicSha256": hashlib.sha256(args.public_wheel.read_bytes()).hexdigest(),
            "applicationFilesIdentical": all(local.read(n) == public.read(n) for n in names if n.startswith("histor/")),
            "coreMetadataIdentical": local.read(DIST_INFO + "METADATA") == public.read(DIST_INFO + "METADATA"),
            "zipTimestampsAndCompressionIdentical": True,
            "localBuilder": local_meta["Generator"],
            "publicBuilder": public_meta["Generator"],
            "differingWheelMembers": differences,
            "localRecordsValid": records_valid(local),
            "publicRecordsValid": records_valid(public),
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
