#!/usr/bin/env python3
"""Read official registry metadata and compare published bytes with frozen artifacts."""

import argparse
import base64
import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MAX_RESPONSE = 16 * 1024 * 1024


def fetch(url, hosts):
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in hosts:
        raise ValueError("unexpected registry host")
    request = Request(url, headers={"User-Agent": "aicom-release-verification/1"})
    with urlopen(request, timeout=60) as response:
        if urlparse(response.url).scheme != "https" or urlparse(response.url).hostname not in hosts:
            raise ValueError("unexpected registry redirect")
        body = response.read(MAX_RESPONSE + 1)
    if len(body) > MAX_RESPONSE:
        raise ValueError("registry response exceeds verification limit")
    return body


def metadata(url, hosts):
    try:
        return json.loads(fetch(url, hosts))
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def wheel_payload(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate wheel member")
        files = {name: archive.read(name) for name in names}
    record_name = "aimarket_histor-0.5.0.dist-info/RECORD"
    records = list(csv.reader(io.StringIO(files[record_name].decode())))
    if len(records) != len(files) or {row[0] for row in records} != set(files):
        raise ValueError("incomplete wheel RECORD")
    for name, digest, size in records:
        if name == record_name:
            if digest or size:
                raise ValueError("unexpected RECORD self digest")
            continue
        actual = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip("=")
        if digest != actual or size != str(len(files[name])):
            raise ValueError("invalid wheel RECORD")
    return files


def verify_recorded_rebuild(local, remote, name):
    # Preserve the original build identity. Recognize only the separately audited
    # public wheel, and independently prove that only its generator/RECORD differ.
    receipt = json.loads((ROOT / "histor/registry-observation/public-receipt.json").read_text())
    expected = next(row["digests"]["sha256"] for row in receipt["files"] if row["filename"] == name)
    if hashlib.sha256(remote).hexdigest() != expected:
        raise ValueError("public wheel differs from audited rebuild")
    left, right = wheel_payload(local), wheel_payload(remote)
    wheel = "aimarket_histor-0.5.0.dist-info/WHEEL"
    record = "aimarket_histor-0.5.0.dist-info/RECORD"
    if set(left) != set(right) or {key for key in left if left[key] != right[key]} != {wheel, record}:
        raise ValueError("public wheel payload differs from local source build")
    if [line for line in left[wheel].splitlines() if line.startswith(b"Generator:")] != [b"Generator: hatchling 1.32.4"]:
        raise ValueError("unexpected local wheel generator")
    if [line for line in right[wheel].splitlines() if line.startswith(b"Generator:")] != [b"Generator: hatchling 1.27.0"]:
        raise ValueError("unexpected public wheel generator")
    left_metadata = [line for line in left[wheel].splitlines() if not line.startswith(b"Generator:")]
    right_metadata = [line for line in right[wheel].splitlines() if not line.startswith(b"Generator:")]
    if left_metadata != right_metadata:
        raise ValueError("public wheel format differs from local build")
    return expected


def verify_pypi():
    manifest = json.loads((ROOT / "histor/artifact-manifest.json").read_text())
    data = metadata("https://pypi.org/pypi/aimarket-histor/0.5.0/json", {"pypi.org"})
    if data is None:
        return {"name": "aimarket-histor", "version": "0.5.0", "status": "not-published"}
    if data["info"]["name"] != "aimarket-histor" or data["info"]["version"] != "0.5.0":
        raise ValueError("PyPI identity mismatch")
    remote_files = {row["filename"]: row for row in data["urls"]}
    results = []
    for kind in ("wheel", "sdist"):
        artifact = manifest["artifactHashes"][kind]
        name = Path(artifact["path"]).name
        local = (ROOT / "histor/artifacts" / name).read_bytes()
        expected = artifact["sha256"]
        if hashlib.sha256(local).hexdigest() != expected:
            raise ValueError("local PyPI artifact changed")
        row = remote_files[name]
        body = fetch(row["url"], {"files.pythonhosted.org"})
        actual = hashlib.sha256(body).hexdigest()
        if row["digests"]["sha256"] != actual:
            raise ValueError("PyPI download differs from registry digest")
        if actual != expected and (kind != "wheel" or verify_recorded_rebuild(local, body, name) != actual):
            raise ValueError("published PyPI artifact hash mismatch")
        results.append({
            "filename": name, "sha256": actual, "bytes": len(body),
            "localBuildSha256": expected, "byteIdenticalToLocalBuild": actual == expected,
            "payloadVerified": True,
        })
    return {"name": "aimarket-histor", "version": "0.5.0", "status": "verified", "files": results}


def verify_npm():
    artifact = json.loads((ROOT / "warden/artifact.json").read_text())
    data = metadata("https://registry.npmjs.org/@aimarket%2fwarden/0.22.2", {"registry.npmjs.org"})
    if data is None:
        return {"name": "@aimarket/warden", "version": "0.22.2", "status": "not-published"}
    if data["name"] != "@aimarket/warden" or data["version"] != "0.22.2":
        raise ValueError("npm identity mismatch")
    local = (ROOT / "warden" / artifact["filename"]).read_bytes()
    if hashlib.sha256(local).hexdigest() != artifact["sha256"]:
        raise ValueError("local npm artifact changed")
    body = fetch(data["dist"]["tarball"], {"registry.npmjs.org"})
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")
    if (
        hashlib.sha256(body).hexdigest() != artifact["sha256"]
        or data["dist"]["integrity"] != artifact["integrity"]
        or integrity != artifact["integrity"]
        or hashlib.sha1(body).hexdigest() != artifact["shasum"]
    ):
        raise ValueError("published npm artifact hash mismatch")
    return {
        "name": data["name"], "version": data["version"], "status": "verified",
        "sha256": artifact["sha256"], "integrity": integrity, "bytes": len(body),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = []
    for name, check in (("PyPI", verify_pypi), ("npm", verify_npm)):
        try:
            checks.append(check())
        except Exception as error:
            # Do not copy response bodies, headers or configuration into evidence.
            checks.append({"registry": name, "status": "error", "errorType": type(error).__name__})
    report = {"checkedAt": datetime.now(UTC).isoformat(), "packages": checks}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if all(row["status"] == "verified" for row in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
