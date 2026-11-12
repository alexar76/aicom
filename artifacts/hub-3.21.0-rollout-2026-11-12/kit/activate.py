"""Make the 3.21.0 wheel authoritative in a legacy /app source-layout hub image (rollout 2026-11-12).

Runs at image build time as root. Replaces /app/aimarket_hub with the wheel's package, byte for byte,
keeping what the wheel does not carry and the hub serves: static/client (the client bundle behind
/clients). Top-level UI files are refreshed from the wheel unless KEEP_UI=1 (Attested keeps its own
navigation in /app/terminal-home.html). The protocol schemas did not change since 3.20.0 and are left alone.
"""
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

W = Path("/tmp/hub321")
WHEEL = W / "aimarket_hub-3.21.0-py3-none-any.whl"
APP = Path("/app")
PACKAGE = APP / "aimarket_hub"
UI_FILES = ("terminal-home.html", "operator.html", "plugins-demo.html",
            "hub-ui-i18n.json", "cap-descriptions-i18n.json", "studio-ui-i18n.json")
keep_ui = os.environ.get("KEEP_UI") == "1"

client = PACKAGE / "static" / "client"
saved = None
if client.is_dir():
    saved = W / "client-saved"
    shutil.copytree(client, saved)

with zipfile.ZipFile(WHEEL) as archive:
    entries = [n for n in archive.namelist() if n.startswith("aimarket_hub/") and not n.endswith("/")]
    assert entries and all(".." not in PurePosixPath(n).parts for n in entries)
    shutil.rmtree(PACKAGE)
    for name in entries:
        target = APP / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
    if saved is not None:
        shutil.copytree(saved, client)
    ui = []
    if not keep_ui:
        for name in UI_FILES:
            shutil.copyfile(PACKAGE / "static" / "ui" / name, APP / name)
            ui.append(name)
    for name in entries:
        assert (APP / name).read_bytes() == archive.read(name), name

legacy = APP / "aimarket_hub.egg-info"
if legacy.exists():
    shutil.rmtree(legacy)

sys.path.insert(0, str(APP))
os.chdir(APP)
import aimarket_hub  # noqa: E402

assert aimarket_hub.__file__.startswith(str(PACKAGE)), aimarket_hub.__file__
assert aimarket_hub.__version__ == importlib.metadata.version("aimarket-hub") == "3.21.0"
result = {"package": str(Path(aimarket_hub.__file__).parent), "version": aimarket_hub.__version__,
          "wheelSha256": hashlib.sha256(WHEEL.read_bytes()).hexdigest(), "filesVerified": len(entries),
          "clientBundleKept": saved is not None, "uiRefreshed": ui}
try:
    result["provenance"] = importlib.metadata.version("aimarket-provenance")
except importlib.metadata.PackageNotFoundError:
    result["provenance"] = None
print(json.dumps(result))
