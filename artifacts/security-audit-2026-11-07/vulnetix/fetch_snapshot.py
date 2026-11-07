"""Read-only immutable snapshot of the public Vulnetix advisory database."""
import concurrent.futures
import datetime
import hashlib
import json
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent


def fetch(url, dest):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "aicom-security-audit/2026-11-07"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            parsed = json.loads(data)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return parsed, {"url": url, "path": str(dest), "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)


def main():
    head, provenance = fetch("https://api.github.com/repos/Vulnetix/advisory-database/commits/main", OUT / "head.json")
    sha = head["sha"]
    base = f"https://raw.githubusercontent.com/Vulnetix/advisory-database/{sha}/"
    manifest, mp = fetch(base + "index/manifest.json", OUT / "manifest.json")
    families = {"PYPI", "NPM", "GO", "CARGO", "VULN-PYPI", "VULN-NPM", "VULN-GO", "VULN-CARGO"}
    selected = [row for row in manifest["records"] if row["family"] in families and row["state"] == "published"]
    print("commit", sha, head["commit"]["committer"]["date"], "records", len(selected), flush=True)
    def get(row):
        data, result = fetch(base + row["paths"]["osv"], OUT / "records" / (row["id"] + ".json"))
        assert data["id"] == row["id"]
        return {**result, "id": row["id"], "classification": row["classification"]}
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for result in pool.map(get, selected):
            records.append(result)
            if len(records) % 200 == 0:
                print("downloaded", len(records), "/", len(selected), flush=True)
    (OUT / "provenance.json").write_text(json.dumps({"commit": sha, "commit_date": head["commit"]["committer"]["date"], "head": provenance, "manifest": mp, "records": records}, indent=2) + "\n")
    print("complete", len(records), flush=True)


if __name__ == "__main__":
    main()
