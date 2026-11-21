#!/usr/bin/env python3
"""New version (v6) of the malware-feed study data on Zenodo: v5 record 23914236 -> v6.

Run with `python3 -I`:
  draft            new version of 23914236, drop the inherited v5 file, upload v6, set metadata,
                   check Zenodo's MD5; writes draft.json
  publish ID       publish draft ID (mints the version DOI); writes published.json
  related ID URL   (draft only) set the isDocumentedBy link to URL

The token is read from ~/.config/zenodo/token and never printed.
"""
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

API = "https://zenodo.org/api/deposit/depositions"
V5_ID = 23914236
HERE = pathlib.Path(__file__).resolve().parent
ARCHIVE = (HERE.parents[2] / "research-data" / "malware-feed-accuracy" / "zenodo-v6"
           / "mfa-study-data-2026-11-21-v6.tar.gz")
SHA256 = "9fd3d695d261f0526f6e273df487ea79eeca93134458695682ac205a0d62122e"
WRITEUP = "https://github.com/alexar76/aicom/blob/main/docs/malware-feed-accuracy.md"

def description(writeup):
    return (
        "<p>Data of an open study of package-malware feeds on npm and PyPI: OpenSSF "
        "<code>malicious-packages</code> with the tools its records name (GitHub's malware advisories among "
        "them) and Vulnetix's GCVE advisory database. Version 6 keeps every file of version 5 (snapshots of "
        "24 October 2026: what the registries did about 242,072 flags, how many flags left up are benign, "
        "what four open scanners catch, what each feed's records show) and adds the repeat measurement of "
        "13 November 2026: the same 7,483 sampled flags checked again, feed withdrawals dated against our "
        "letters, new flags, six scanners on a second week of uploads and on DataDog's malware set read by "
        "people, Vulnetix's STIX indicators against the Tranco top 10,000, and the readings behind them.</p>"
        "<p>The method was fixed before the results, and the repeat date before any feed data was read. No "
        "package file is included, and the names of packages read as benign are withheld. "
        "<code>code/verify_archive.py</code> and <code>code/repeat/verify_repeat.py</code> recompute every "
        "number from these files. The report in five languages is in <code>report/</code>. The data are "
        "CC BY 4.0; the code inside the archive is MIT, as its README says.</p>"
        f"<p>Write-up: <a href=\"{writeup}\">{writeup}</a></p>")

def metadata(writeup):
    return {
        "upload_type": "dataset",
        "title": "Package-malware feeds on npm and PyPI: study data, 2026-10 and the repeat of 2026-11-13",
        "creators": [{"name": "Artamokhov, Aleksandr"}],
        "description": description(writeup),
        "version": "2026-11-21-v6",
        "publication_date": "2026-11-21",
        "access_right": "open",
        "license": "cc-by-4.0",
        "keywords": ["malware", "npm", "PyPI", "software supply chain", "threat intelligence",
                     "false positives", "open data", "repeat measurement"],
        "related_identifiers": [{"identifier": writeup, "relation": "isDocumentedBy",
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
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw; headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = r.read()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode(errors='replace')[:2000]}")

def draft():
    blob = ARCHIVE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA256:
        sys.exit("archive SHA-256 differs from the recorded one")
    nv = call("POST", f"{API}/{V5_ID}/actions/newversion")
    dep = call("GET", nv["links"]["latest_draft"])
    for f in dep.get("files", []):
        call("DELETE", f["links"]["self"])
    up = call("PUT", f"{dep['links']['bucket']}/{ARCHIVE.name}", raw=blob)
    if up.get("checksum") != "md5:" + hashlib.md5(blob).hexdigest():
        sys.exit(f"MD5 mismatch after upload: {up.get('checksum')}")
    dep = call("PUT", f"{API}/{dep['id']}", body={"metadata": metadata(WRITEUP)})
    (HERE / "draft.json").write_text(json.dumps(dep, indent=1, ensure_ascii=False) + "\n")
    print("draft", dep["id"], "files", [f["filename"] for f in dep.get("files", [])],
          "prereserved doi", dep["metadata"].get("prereserve_doi", {}).get("doi"))

def related(dep_id, url):
    dep = call("PUT", f"{API}/{dep_id}", body={"metadata": metadata(url)})
    (HERE / "draft.json").write_text(json.dumps(dep, indent=1, ensure_ascii=False) + "\n")
    print("updated", dep_id, url)

def publish(dep_id):
    dep = call("POST", f"{API}/{dep_id}/actions/publish")
    (HERE / "published.json").write_text(json.dumps(dep, indent=1, ensure_ascii=False) + "\n")
    print("published", dep.get("doi"), dep.get("conceptdoi"), dep["links"].get("record_html") or dep["links"].get("html"))

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["draft"]: draft()
    elif a[:1] == ["publish"] and len(a) == 2: publish(a[1])
    elif a[:1] == ["related"] and len(a) == 3: related(a[1], a[2])
    else: sys.exit(__doc__)
