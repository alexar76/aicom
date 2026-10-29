"""Fetch exact public PyPI wheels, verify hashes and compare shipped Python code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RELEASES = [
    ("aimarket-oracle-gateway", "0.3.2", "plugins/aimarket-oracle-gateway", "aimarket_oracle_gateway"),
    ("aimarket-mcp-packager", "2.1.2", "plugins/aimarket-mcp-packager", "aimarket_mcp_packager"),
    ("aimarket-metis", "0.2.4", "metis", "metis"),
]


def get(url, limit=32_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": "alexar76-pypi-release-verification/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Response exceeds inspection bound")
        return data


def check(item):
    name, version, project, package = item
    result = {"name": name, "requestedVersion": version,
              "checkedAt": datetime.now(timezone.utc).isoformat()}
    try:
        endpoint = f"https://pypi.org/pypi/{name}/{version}/json"
        metadata = json.loads(get(endpoint))
        (OUT / f"{name}-{version}-pypi.json").write_text(json.dumps(metadata, indent=2) + "\n")
        assert metadata["info"]["version"] == version
        result.update(version=version, projectUrl=f"https://pypi.org/project/{name}/{version}/",
                      requiresDist=metadata["info"].get("requires_dist"))
        wheels = [entry for entry in metadata["urls"] if entry["packagetype"] == "bdist_wheel"]
        assert len(wheels) == 1 and not wheels[0]["yanked"], "Expected one non-yanked wheel"
        wheel = wheels[0]
        assert wheel["url"].startswith("https://files.pythonhosted.org/")
        data = get(wheel["url"])
        digest = hashlib.sha256(data).hexdigest()
        assert digest == wheel["digests"]["sha256"]
        folder = OUT / "wheels"
        folder.mkdir(exist_ok=True)
        (folder / wheel["filename"]).write_bytes(data)
        local = ROOT / project / package
        local_files = {file.relative_to(ROOT / project).as_posix(): file.read_bytes()
                       for file in local.rglob("*.py") if "__pycache__" not in file.parts}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            shipped = {file: archive.read(file) for file in archive.namelist()
                       if file.startswith(package + "/") and file.endswith(".py")}
            differences = [file for file in sorted(local_files.keys() | shipped.keys())
                           if local_files.get(file) != shipped.get(file)]
        result.update(status="ok", wheelFilename=wheel["filename"], sha256=digest,
                      uploadedAt=wheel["upload_time_iso_8601"], wheelUrl=wheel["url"],
                      sourceFiles=len(shipped), sourceDifferences=differences,
                      sourceMatchesWorkspace=not differences)
    except Exception as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    return result


with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(check, RELEASES))
(OUT / "registry-verification.json").write_text(json.dumps(results, indent=2) + "\n")
for result in results:
    print(result["name"], result["requestedVersion"], result["status"],
          "source matches:", result.get("sourceMatchesWorkspace"), result.get("error", ""))
assert all(result["status"] == "ok" and result["sourceMatchesWorkspace"] for result in results)
