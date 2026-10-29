"""List-only full observations of exact first-party Python wheels under one fixed SDK profile.

Uses the previously installed clean release environment, with no installs or tools/call.
Current pairs measure stability. Version pairs are controlled replays performed now.
"""

from __future__ import annotations

import copy
import hashlib
import json
import queue
import subprocess
import sys
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENV = Path("/private/tmp/pypi-mcp-releases-20261027")
PYTHON = ENV / "bin/python"
sys.path.insert(0, str(ROOT / "histor"))

from histor.upgrade_brief import _validate_snapshot
from histor.toolcost_cli import _Stdio

CLEAN_ENV = {"PATH": str(ENV / "bin") + ":/usr/bin:/bin"}
PACKAGES = {
    "oracle-gateway": {"distribution": "aimarket-oracle-gateway", "module": "aimarket_oracle_gateway",
                       "versions": ("0.3.1", "0.3.2")},
    "packager": {"distribution": "aimarket-mcp-packager", "module": "aimarket_mcp_packager",
                 "versions": ("2.1.1", "2.1.2")},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


class Recorder(_Stdio):
    def __init__(self, argv, cwd, stderr):
        self.events = []
        self.deadline = time.monotonic() + 25
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=stderr, cwd=cwd, env=CLEAN_ENV)
        self.inbox = queue.Queue()
        self.next_id = 0
        self.modern = True
        self.protocol_version = None
        self.server_info = None
        threading.Thread(target=self._read, daemon=True).start()

    def send(self, message):
        method = message.get("method")
        assert method in {"server/discover", "initialize", "notifications/initialized", "tools/list", None}, method
        assert method is not None or "error" in message
        self.events.append({"direction": "client", "message": copy.deepcopy(message)})
        return super().send(message)

    def request(self, method, params, wait_s=None):
        result = super().request(method, params, wait_s)
        self.events.append({"direction": "server", "method": method, "result": copy.deepcopy(result)})
        return result


def inventory():
    command = [str(PYTHON), "-I", "-B", "-c", "import importlib.metadata,json,platform; print(json.dumps({"
               "'python':platform.python_version(),'platform':platform.platform(),"
               "'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()}}))"]
    result = subprocess.run(command, env=CLEAN_ENV, capture_output=True, text=True, timeout=15, check=True)
    data = json.loads(result.stdout)
    data["interpreterPath"] = str(PYTHON)
    data["interpreterResolved"] = str(PYTHON.resolve())
    data["interpreterSha256"] = sha(PYTHON.resolve())
    assert data["packages"]["aimarket-oracle-gateway"] == "0.3.2"
    assert data["packages"]["aimarket-mcp-packager"] == "2.1.2"
    assert data["packages"]["mcp"] == "1.30.0"
    return data


def artifacts():
    downloads = json.loads((HERE / "old-wheel-downloads.json").read_text())
    result = {}
    for label, spec in PACKAGES.items():
        for version in spec["versions"]:
            filename = spec["module"] + "-" + version + "-py3-none-any.whl"
            wheel = HERE / "wheels" / filename
            if not wheel.exists():
                wheel = ROOT / "docs/evidence/pypi-mcp-release-verification-2026-10-27/wheels" / filename
            assert wheel.is_file(), wheel
            if version == spec["versions"][0]:
                record = next(item for item in downloads if item["filename"] == filename)
                expected_hash = record["sha256"]
            else:
                metadata_path = ROOT / "docs/evidence/pypi-mcp-release-verification-2026-10-27" / (spec["distribution"] + "-" + version + "-pypi.json")
                metadata = json.loads(metadata_path.read_text())
                records = metadata.get("urls", []) or metadata["releases"][version]
                record = next(item for item in records if item["filename"] == filename)
                expected_hash = record["digests"]["sha256"]
            assert sha(wheel) == expected_hash
            target = HERE / "artifacts" / (label + "-" + version)
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(wheel) as archive:
                for member in archive.infolist():
                    path = Path(member.filename)
                    assert not path.is_absolute() and ".." not in path.parts
                    assert not member.is_dir() or member.filename.endswith("/")
                    assert member.file_size < 2_000_000
                archive.extractall(target)
            files = [{"path": str(path.relative_to(target)), "sha256": sha(path)}
                     for path in sorted(target.rglob("*.py"))]
            result[label, version] = {"wheel": str(wheel.relative_to(ROOT)), "sha256": expected_hash,
                                      "extractedPath": str(target), "pythonFiles": files}
    return result


def capture(label, version, name, runtime, wheels):
    spec = PACKAGES[label]
    record = wheels[label, version]
    active = HERE / "active" / label
    active.parent.mkdir(exist_ok=True)
    if active.is_symlink():
        active.unlink()
    assert not active.exists()
    active.symlink_to(Path(record["extractedPath"]))
    cwd = HERE / "run-state" / label
    cwd.mkdir(parents=True, exist_ok=True)
    argv = [str(PYTHON), "-I", "-B", str(HERE / "launch_list_only.py"),
            "--module", spec["module"] + ".stdio_server", "--overlay", str(active)]
    dependencies = {k: v for k, v in runtime["packages"].items()
                    if k not in {item["distribution"] for item in PACKAGES.values()}}
    lock = "sha256:" + hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()
    launch = {
        "transport": "stdio", "entrypoint": spec["module"] + ".stdio_server",
        "argv": argv, "cwd": str(cwd),
        "runtime": {"python": runtime["python"], "interpreterSha256": runtime["interpreterSha256"]},
        "dependencyProfile": {"mcp": runtime["packages"]["mcp"], "environmentLockSha256": lock},
        "environment": {"policy": "allowlist", "names": ["PATH"], "credentials": "absent"},
        "guard": {"network": "Python audit hook denies DNS and socket connections",
                  "subprocess": "Python audit hook denies child processes", "osSandbox": False},
    }
    snapshot_path = HERE / "snapshots" / (name + ".json")
    assert not snapshot_path.exists(), "choose new names for new captures"
    client = None
    tools = None
    error = None
    with (HERE / (name + "-stderr.log")).open("wb") as stderr:
        try:
            client = Recorder(argv, cwd, stderr)
            tools = client.tools()
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)[:1000]}
        finally:
            if client is not None:
                client.close()
    info = client.server_info or {} if client else {}
    snapshot = {
        "format": "histor.upgrade-observation/v1", "targetId": "pypi:" + spec["distribution"],
        "status": "ok" if tools is not None else "failed",
        "observedAt": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "packageVersion": version, "serverName": info.get("name"), "serverVersion": info.get("version"),
        "protocol": client.protocol_version if client else None, "launch": launch, "extrasCoverage": "observed",
    }
    if tools is not None:
        snapshot["tools"] = tools
    _validate_snapshot(snapshot)
    save(snapshot_path, snapshot)
    evidence = {"label": name, "purpose": "fresh current baseline/recheck" if name.startswith("current-") else "controlled version replay now",
                "snapshot": str(snapshot_path.relative_to(ROOT)), "snapshotSha256": sha(snapshot_path),
                "artifact": record, "actualArgv": argv, "resolvedOverlay": str(active.resolve()),
                "sourceFilesSha256": {"capture": sha(Path(__file__)), "launcher": sha(HERE / "launch_list_only.py"),
                                     "reader": sha(ROOT / "histor/histor/toolcost_cli.py")},
                "protocol": snapshot["protocol"], "serverInfo": info, "toolCount": len(tools or []),
                "toolCalls": 0, "error": error, "events": client.events if client else [],
                "stderr": name + "-stderr.log"}
    save(HERE / (name + "-evidence.json"), evidence)
    print(json.dumps({"name": name, "status": snapshot["status"], "packageVersion": version,
                      "protocol": snapshot["protocol"], "toolCount": len(tools or []), "error": error}))
    return snapshot


def main():
    runtime = inventory()
    save(HERE / "runtime.json", runtime)
    wheels = artifacts()
    save(HERE / "artifact-index.json", [{"package": key[0], "version": key[1], **value} for key, value in wheels.items()])
    for phase in ("baseline", "recheck"):
        for label, spec in PACKAGES.items():
            capture(label, spec["versions"][1], f"current-{label}-{phase}", runtime, wheels)
    for label, spec in PACKAGES.items():
        for side, version in zip(("before", "after"), spec["versions"], strict=True):
            capture(label, version, f"upgrade-{label}-{side}", runtime, wheels)


if __name__ == "__main__":
    main()
