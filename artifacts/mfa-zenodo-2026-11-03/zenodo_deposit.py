#!/usr/bin/env python3
"""Deposit the malware-feed study archive (v5) on Zenodo.

Two steps, run with `python3 -I`:
  draft            create the deposition, upload the archive, set the metadata,
                   check Zenodo's MD5 against the local file; writes draft.json
  publish ID       publish deposition ID (mints the DOI); writes published.json

The token is read from ~/.config/zenodo/token (scopes deposit:write and
deposit:actions) and is never printed.
"""
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

API = "https://zenodo.org/api/deposit/depositions"
HERE = pathlib.Path(__file__).resolve().parent
ARCHIVE = HERE.parent / "vulnetix-prepub-check-2026-11-02" / "mfa-study-data-2026-10-29-v5.tar.gz"
SHA256 = "03e578baed77b84a06c72722680d4c2d19399401c80744caf1fff73032e91054"
WRITEUP = ("https://github.com/alexar76/aicom/blob/7ae8dbc407a736d8469e647e75a012b1e7d1bdfa/"
           "docs/malware-feed-accuracy.md")

DESCRIPTION = (
    "<p>Data of an open study of package-malware feeds on npm and PyPI: OpenSSF "
    "<code>malicious-packages</code> with the tools its records name (GitHub's malware advisories "
    "among them) and Vulnetix's GCVE advisory database as it stood on 24 October 2026. It covers what "
    "the registries did about 242,072 flags (stage 1, a stratified sample of 7,483), how many of the "
    "flags registries left up are benign (stage 2, two model raters and human adjudication), what four "
    "open scanners catch and how many false alarms they raise (stage 3), and what each feed's records "
    "show and how feeds answer disputes (section 9).</p>"
    "<p>The method was fixed before the results. No package file is included, and the names of "
    "packages read as benign are withheld. <code>code/verify_archive.py</code> recomputes every number "
    "from these files. The data are CC BY 4.0; the code inside the archive is MIT, as its README says.</p>"
    f"<p>Write-up: <a href=\"{WRITEUP}\">{WRITEUP}</a></p>"
)

METADATA = {
    "upload_type": "dataset",
    "title": "Package-malware feeds on npm and PyPI: study data, 2026-10",
    "creators": [{"name": "Artamokhov, Aleksandr"}],
    "description": DESCRIPTION,
    "version": "2026-10-29-v5",
    "publication_date": "2026-11-03",
    "access_right": "open",
    "license": "cc-by-4.0",
    "keywords": ["malware", "npm", "PyPI", "software supply chain", "threat intelligence",
                 "false positives", "open data"],
    "related_identifiers": [{"identifier": WRITEUP, "relation": "isDocumentedBy",
                             "resource_type": "publication-report"}],
}


def token():
    t = (pathlib.Path.home() / ".config" / "zenodo" / "token").read_text().strip()
    if not t:
        sys.exit("empty token file")
    return t


def call(method, url, body=None, raw=None):
    headers = {"Authorization": "Bearer " + token()}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode(errors='replace')[:2000]}")


def draft():
    blob = ARCHIVE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA256:
        sys.exit("archive SHA-256 differs from the recorded one")
    dep = call("POST", API, body={})
    up = call("PUT", f"{dep['links']['bucket']}/{ARCHIVE.name}", raw=blob)
    if up.get("checksum") != "md5:" + hashlib.md5(blob).hexdigest():
        sys.exit(f"MD5 mismatch after upload: {up.get('checksum')}")
    dep = call("PUT", f"{API}/{dep['id']}", body={"metadata": METADATA})
    (HERE / "draft.json").write_text(json.dumps(dep, indent=1, ensure_ascii=False) + "\n")
    print("draft", dep["id"], dep["links"]["html"], "size", up.get("size"), up.get("checksum"))


def publish(dep_id):
    dep = call("POST", f"{API}/{dep_id}/actions/publish")
    (HERE / "published.json").write_text(json.dumps(dep, indent=1, ensure_ascii=False) + "\n")
    print("published", dep.get("doi"), dep.get("conceptdoi"), dep["links"].get("record_html") or dep["links"].get("html"))


if __name__ == "__main__":
    if sys.argv[1:2] == ["draft"]:
        draft()
    elif sys.argv[1:2] == ["publish"] and len(sys.argv) == 3:
        publish(sys.argv[2])
    else:
        sys.exit(__doc__)
