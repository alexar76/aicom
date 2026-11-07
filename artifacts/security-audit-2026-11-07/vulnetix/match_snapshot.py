"""Match the immutable public snapshot offline; preserve unverified version alerts."""
import collections
import datetime
import importlib.util
import json
import tomllib
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
spec = importlib.util.spec_from_file_location("offline", ROOT / "artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py")
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)
scan = offline.scan


def main():
    provenance = json.loads((OUT / "provenance.json").read_text())
    snapshot = {row["id"] for row in provenance["records"]}
    paths = list((OUT / "records").glob("*.json"))
    assert snapshot == {p.stem for p in paths}, "Incomplete or contaminated advisory snapshot"
    packages, owners = scan.collect(ROOT)
    index = collections.defaultdict(list)
    for ecosystem, name, version in packages:
        index[(ecosystem, offline.normalize(ecosystem, name))].append({
            "ecosystem": ecosystem, "package": name, "version": version,
            "paths": sorted(owners[(ecosystem, name, version)]), "owned": False,
        })
    owned = []
    for base, files in scan.walk(ROOT):
        if base.is_relative_to(ROOT / "docs/evidence"):
            continue
        for filename in ("package.json", "pyproject.toml"):
            if filename not in files:
                continue
            path = base / filename
            data = json.loads(path.read_text()) if filename == "package.json" else tomllib.loads(path.read_text()).get("project", {})
            if not data.get("name") or not data.get("version"):
                continue
            eco = "npm" if filename == "package.json" else "PyPI"
            row = {"ecosystem": eco, "package": data["name"], "version": data["version"],
                   "paths": [str(path.relative_to(ROOT))], "owned": True}
            owned.append(row)
            index[(eco, offline.normalize(eco, data["name"]))].append(row)
    hits, errors, relevant = [], [], {}
    for path in paths:
        advisory = json.loads(path.read_text())
        if advisory.get("withdrawn"):
            continue
        for affected in advisory.get("affected", []):
            package = affected.get("package", {})
            eco, name = package.get("ecosystem"), package.get("name", "")
            candidates = index[(eco, offline.normalize(eco, name))]
            for row in candidates:
                if row["owned"]:
                    relevant[advisory["id"]] = {"id": advisory["id"], "package": name, "summary": advisory.get("summary"), "details": advisory.get("details"), "affected": advisory["affected"], "modified": advisory.get("modified")}
                try:
                    match = offline.affected(eco, row["version"], affected)
                except Exception as exc:
                    errors.append({"id": advisory["id"], **row, "error": str(exc)})
                    continue
                if match:
                    hits.append({**row, "id": advisory["id"], "summary": advisory.get("summary"),
                                 "severity": scan.severity_of(advisory),
                                 "classification": advisory.get("database_specific", {}).get("vulnetix", {}).get("classification"),
                                 "fixed": scan.fixed_versions(advisory, eco, name),
                                 "references": advisory.get("references", [])})
    summary = {"scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "commit": provenance["commit"], "commit_date": provenance["commit_date"],
               "records_checked": len(paths), "dependency_package_versions": len(packages),
               "owned_package_versions": len(owned), "owned_advisories_reviewed": len(relevant),
               "matches": hits, "errors": errors}
    for name, data in (("matches.json", summary), ("owned-packages.json", owned), ("owned-advisories.json", list(relevant.values()))):
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"matches", "errors"}}, indent=2))
    print("MATCHES", len(hits), "ERRORS", len(errors))
    for row in hits:
        print(row["id"], row["package"], row["version"], "owned", row["owned"], row["summary"])


if __name__ == "__main__":
    main()
