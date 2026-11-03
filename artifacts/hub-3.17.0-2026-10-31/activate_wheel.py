"""Make the release wheel authoritative in the legacy /app source-layout image."""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.metadata
import json
import shutil
import zipfile

wheel = Path("/tmp/aimarket_hub-3.17.0-py3-none-any.whl")
package = Path("/app/aimarket_hub")
with zipfile.ZipFile(wheel) as archive:
    entries = [n for n in archive.namelist() if n.startswith("aimarket_hub/") and not n.endswith("/")]
    assert entries and all(".." not in PurePosixPath(n).parts for n in entries)
    if package.exists():
        shutil.rmtree(package)
    for name in entries:
        target = Path("/app") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
    for name in ("terminal-home.html", "operator.html", "plugins-demo.html", "hub-ui-i18n.json",
                 "cap-descriptions-i18n.json", "studio-ui-i18n.json"):
        shutil.copyfile(package / "static/ui" / name, Path("/app") / name)
    for name in entries:
        assert (Path("/app") / name).read_bytes() == archive.read(name)
legacy = Path("/app/aimarket_hub.egg-info")
if legacy.exists():
    shutil.rmtree(legacy)
import aimarket_hub
assert aimarket_hub.__version__ == importlib.metadata.version("aimarket-hub") == "3.17.0"
print(json.dumps({"package": str(Path(aimarket_hub.__file__).parent), "version": aimarket_hub.__version__,
                  "wheelSha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "filesVerified": len(entries)}))
