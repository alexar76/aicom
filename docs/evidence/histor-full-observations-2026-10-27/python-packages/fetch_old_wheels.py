"""Fetch two exact first-party wheels from saved official PyPI URLs and verify their hashes."""

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
items = []
for name, version in (("aimarket-oracle-gateway", "0.3.1"), ("aimarket-mcp-packager", "2.1.1")):
    source = ROOT / "docs/evidence/mcp-current-recheck-2026-10-27" / (name + "-registry.json")
    registry = json.loads(source.read_text())
    item = next(item for item in registry["releases"][version] if item["filename"].endswith(".whl"))
    assert item["url"].startswith("https://files.pythonhosted.org/")
    path = HERE / "wheels" / item["filename"]
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(item["url"], timeout=20) as response:
            assert response.geturl().startswith("https://files.pythonhosted.org/")
            data = response.read(5_000_001)
    assert len(data) < 5_000_001
    assert hashlib.sha256(data).hexdigest() == item["digests"]["sha256"]
    path.write_bytes(data)
    items.append({"distribution": name, "version": version, "url": item["url"],
                  "filename": item["filename"], "sha256": item["digests"]["sha256"], "bytes": len(data),
                  "sourceMetadata": str(source.relative_to(ROOT))})
(HERE / "old-wheel-downloads.json").write_text(json.dumps(items, indent=2) + "\n")
print(json.dumps(items))
