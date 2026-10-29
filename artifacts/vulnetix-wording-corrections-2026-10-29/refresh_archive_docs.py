#!/usr/bin/env python3
"""Refresh documentation in the already-redacted DOI archive without changing data.

The input archive is fixed by checksum. Every stage 1/2/3 byte, including its
random identifiers, stays unchanged. Existing code/report members are read from
one exact repository commit. No private study inputs are read. The result is a
new archive; the original is never overwritten.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


BASE_SHA256 = "e117f283951060cf1c1ba19b8b868830ad84d859010097ca30f0207cf97a3b60"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_archive(path: Path) -> dict[str, bytes]:
    blobs = {}
    roots = set()
    with tarfile.open(path) as source:
        for member in source.getmembers():
            path_parts = PurePosixPath(member.name).parts
            if not path_parts or path_parts[0] in (".", "..") or ".." in path_parts:
                raise ValueError("Unsafe archive member")
            roots.add(path_parts[0])
            if member.isdir():
                continue
            if not member.isfile() or len(path_parts) < 2:
                raise ValueError("Only regular archive files are supported")
            relative = str(PurePosixPath(*path_parts[1:]))
            if relative in blobs:
                raise ValueError("Duplicate archive member")
            blobs[relative] = source.extractfile(member).read()
    if len(roots) != 1:
        raise ValueError("Expected one archive root")
    return blobs


def verify_sums(blobs: dict[str, bytes]) -> int:
    rows = blobs["SHA256SUMS"].decode().splitlines()
    seen = set()
    for row in rows:
        wanted, relative = row.split("  ", 1)
        if relative in seen or digest(blobs[relative]) != wanted:
            raise ValueError("Archive checksum mismatch")
        seen.add(relative)
    if seen != set(blobs) - {"SHA256SUMS"}:
        raise ValueError("Checksum manifest does not cover every file")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    if digest(source_bytes) != BASE_SHA256:
        raise ValueError("The input is not the verified 29 October archive")
    if args.out.exists() or args.out.suffixes[-2:] != [".tar", ".gz"]:
        raise ValueError("Output must be a new .tar.gz file")
    report_path = args.out.with_name(args.out.name.removesuffix(".tar.gz") + ".refresh.json")
    if report_path.exists():
        raise ValueError("Refusing to overwrite an existing refresh report")

    commit = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", args.commit + "^{commit}"], text=True
    ).strip()
    before = load_archive(args.source)
    source_sum_count = verify_sums(before)
    after = dict(before)
    changed = []
    source_members = {}
    for relative in sorted(before):
        if relative.startswith("code/"):
            repository_path = "research/malware-feed-accuracy/" + relative[len("code/"):]
        elif relative.startswith("report/"):
            repository_path = "docs/" + relative[len("report/"):]
        else:
            continue
        payload = subprocess.check_output(
            ["git", "-C", str(args.repo), "show", commit + ":" + repository_path]
        )
        after[relative] = payload
        source_members[relative] = digest(payload)
        if payload != before[relative]:
            changed.append(relative)

    data_members = sorted(name for name in before if name.startswith(("stage1/", "stage2/", "stage3/")))
    if not data_members or any(after[name] != before[name] for name in data_members):
        raise ValueError("Study data changed during a documentation refresh")

    base_build = json.loads(before["BUILD.json"])
    build = copy.deepcopy(base_build)
    build["commit"] = commit
    build["documentation_refresh"] = {
        "base_archive_sha256": BASE_SHA256,
        "base_source_commit": base_build["commit"],
        "data_files_preserved_byte_for_byte": len(data_members),
        "random_identifiers_preserved": True,
        "privacy_basis": "Previously redacted data are unchanged; no private input was read.",
        "base_privacy_scan": {
            "blocking_leaks": base_build.get("blocking_leaks"),
            "names_for_review": base_build.get("names_for_review"),
        },
    }
    # The original leak-scan counts describe the base build. They are recorded
    # explicitly above instead of implying that a private-input scan ran again.
    build.pop("blocking_leaks", None)
    build.pop("names_for_review", None)
    after["BUILD.json"] = (json.dumps(build, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()
    after["SHA256SUMS"] = "".join(
        digest(payload) + "  " + relative + "\n"
        for relative, payload in sorted(after.items()) if relative != "SHA256SUMS"
    ).encode()
    sum_count = verify_sums(after)
    if sum_count != source_sum_count:
        raise ValueError("Unexpected change in archive file count")

    checks = []
    with tempfile.TemporaryDirectory(prefix="mfa-wording-archive-") as temp:
        tree = Path(temp)
        for relative, payload in after.items():
            destination = tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        for _ in range(3):
            completed = subprocess.run(
                [sys.executable, "-I", str(tree / "code/verify_archive.py"), str(tree)],
                capture_output=True, text=True, check=True,
            )
            if "ALL SAME" not in completed.stdout:
                raise ValueError("Archive verification did not report ALL SAME")
            checks.append({"exit_code": completed.returncode, "stdout": completed.stdout.strip()})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    archive_root = args.out.name.removesuffix(".tar.gz")
    with args.out.open("xb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for relative, payload in sorted(after.items()):
                    info = tarfile.TarInfo(archive_root + "/" + relative)
                    info.size = len(payload)
                    info.mode = 0o644
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(payload))
    reloaded = load_archive(args.out)
    if reloaded != after:
        raise ValueError("Final archive differs from the verified refresh tree")
    report = {
        "kind": "documentation-only refresh",
        "source_archive_sha256": BASE_SHA256,
        "source_archive_commit": base_build["commit"],
        "documentation_commit": commit,
        "output": str(args.out.resolve()),
        "sha256": digest(args.out.read_bytes()),
        "bytes": args.out.stat().st_size,
        "sha256sums_rows": verify_sums(reloaded),
        "unchanged_data_files": len(data_members),
        "data_and_random_ids_unchanged": True,
        "changed_code_or_report_members": changed,
        "source_member_sha256": source_members,
        "verification_runs": checks,
        "private_study_inputs_read": False,
        "original_archive_unchanged": digest(args.source.read_bytes()) == BASE_SHA256,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in (
        "output", "sha256", "bytes", "sha256sums_rows", "unchanged_data_files",
        "data_and_random_ids_unchanged", "changed_code_or_report_members",
    )}, indent=2))
    print("ALL SAME (3 verification runs)")
    print("Report:", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
