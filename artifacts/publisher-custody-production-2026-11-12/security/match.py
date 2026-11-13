"""Match public advisory snapshots against the recorded production Python inventory offline."""

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "osv_matcher", ROOT / "artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py"
)
matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matcher)


def load(path):
    return json.loads(path.read_text())


def write(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def provenance(path, url):
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest, "url": url,
            "retrieved_at_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()}


def compare(records, inventory):
    index = {}
    for row in inventory:
        index.setdefault(matcher.normalize("PyPI", row["name"]), set()).add(row["version"])
    findings, errors, seen = [], [], set()
    families = Counter()
    for record in records:
        if record.get("withdrawn"):
            continue
        identifier = record["id"]
        seen.add(identifier)
        family = next((prefix for prefix in ("GHSA", "PYSEC", "CVE", "GCVE", "MAL")
                       if identifier.startswith(prefix + "-")), "other")
        families[family] += 1
        for affected in record.get("affected", []):
            package = affected.get("package", {})
            if package.get("ecosystem") != "PyPI":
                continue
            name = matcher.normalize("PyPI", package["name"])
            for version in sorted(index.get(name, ())):
                try:
                    matched = matcher.affected("PyPI", version, affected)
                except (TypeError, ValueError) as exc:
                    errors.append({"id": identifier, "package": name, "version": version, "error": str(exc)})
                    continue
                if matched:
                    findings.append({"id": identifier, "aliases": record.get("aliases", []), "package": name,
                                     "version": version, "severity": matcher.scan.severity_of(record),
                                     "summary": record.get("summary", ""),
                                     "fixed": matcher.scan.fixed_versions(record, "PyPI", package["name"])})
    return {"records_checked": len(seen), "record_families": dict(sorted(families.items())),
            "findings": findings, "matching_errors": errors}


def osv_records(archive):
    with zipfile.ZipFile(archive) as data:
        for filename in data.namelist():
            if filename.endswith(".json"):
                yield json.loads(data.read(filename))


def vulnetix_snapshot():
    repository = CACHE / "vulnetix"
    head = load(CACHE / "vulnetix-head.json")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if commit != head["sha"]:
        raise ValueError("Vulnetix sparse checkout is not at the expected immutable commit")
    manifest = load(CACHE / "vulnetix-manifest.json")
    selected = [row for row in manifest["records"] if row["family"] in {"PYPI", "VULN-PYPI", "OSM"}
                and row["state"] == "published"]
    data = []
    digest = hashlib.sha256()
    for row in sorted(selected, key=lambda item: item["id"]):
        contents = (repository / row["paths"]["osv"]).read_bytes()
        record = json.loads(contents)
        if record["id"] != row["id"] or record.get("withdrawn"):
            raise ValueError(f"mismatched record {row['id']}")
        digest.update(row["id"].encode() + b"\0" + hashlib.sha256(contents).digest())
        data.append(record)
    return data, {"commit": commit, "commit_date": head["commit"]["committer"]["date"],
                  "record_tree_sha256": digest.hexdigest(),
                  "families": dict(Counter(row["family"] for row in selected)),
                  "manifest": provenance(CACHE / "vulnetix-manifest.json",
                                         f"https://raw.githubusercontent.com/Vulnetix/advisory-database/{commit}/index/manifest.json")}


def kev_matches(findings):
    path = CACHE / "cisa-kev.json"
    catalog = load(path)
    cves = {value for finding in findings for value in (finding["id"], *finding["aliases"])
            if re.fullmatch(r"CVE-\d{4}-\d+", value)}
    return {"catalog_version": catalog["catalogVersion"], "records_checked": len(catalog["vulnerabilities"]),
            "affected_cve_matches": sorted(cves & {row["cveID"] for row in catalog["vulnerabilities"]}),
            "dataset": provenance(path, "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")}


def main():
    source = HERE / (sys.argv[3] if len(sys.argv) > 3 else "apex-installed.json")
    inventory = load(source)
    archive = CACHE / "PyPI.zip"
    result = {"checked_at_utc": datetime.now(UTC).isoformat(), "inventory": source.name,
              "image": inventory["image"], "python": inventory["python"],
              "package_count": len(inventory["packages"]), "osv": {
                  **compare(osv_records(archive), inventory["packages"]),
                  "dataset": provenance(archive, "https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip")}}
    if len(sys.argv) <= 2 or sys.argv[2] != "--osv-only":
        advisories, details = vulnetix_snapshot()
        result["vulnetix"] = {**compare(advisories, inventory["packages"]), "dataset": details}
    result["cisa_kev"] = kev_matches(result["osv"]["findings"] + result.get("vulnetix", {}).get("findings", []))
    write("advisory-results.json" if "vulnetix" in result else "osv-precheck.json", result)
    for name in ("osv", "vulnetix"):
        if name in result:
            data = result[name]
            print(f"{name}: {data['records_checked']} advisories, {len(data['findings'])} findings, "
                  f"{len(data['matching_errors'])} matching errors")
            for row in data["findings"] + data["matching_errors"]:
                print(row["id"], row["package"], row["version"], row.get("severity", row.get("error")))
    print(f"CISA KEV: {result['cisa_kev']['records_checked']} entries, {result['cisa_kev']['affected_cve_matches']}")


if __name__ == "__main__":
    main()
