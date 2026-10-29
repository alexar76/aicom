"""Replay exact Oracle 0.3.1 and 0.3.2 wheel startup using one installed SDK profile.

Only initialize, initialized notification and tools/list are sent. No network or installs.
"""

from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PYTHON = Path("/private/tmp/pypi-mcp-releases-20261027/bin/python")
ORIGINAL = ROOT / "docs/evidence/histor-full-observations-2026-10-27/python-packages"
CLEAN_ENV = {"PATH": str(PYTHON.parent) + ":/usr/bin:/bin"}
VERSIONS = ("0.3.1", "0.3.2")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


class Client:
    def __init__(self, argv, cwd, stderr):
        self.events = []
        self.raw_stdout = []
        self.next_id = 0
        self.until = time.monotonic() + 20
        self.inbox = queue.Queue()
        self.proc = subprocess.Popen(argv, cwd=cwd, env=CLEAN_ENV, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=stderr)
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        try:
            while raw := self.proc.stdout.readline(2_000_001):
                if len(raw) > 2_000_000:
                    self.inbox.put(RuntimeError("stdout line exceeded bound"))
                    return
                self.raw_stdout.append(raw.decode("utf-8", errors="replace"))
                try:
                    message = json.loads(raw)
                except ValueError:
                    self.inbox.put(RuntimeError("non-JSON stdout during MCP startup"))
                    return
                self.events.append({"direction": "server", "message": message})
                self.inbox.put(message)
        finally:
            self.inbox.put(None)

    def send(self, message):
        assert message.get("method") in {"initialize", "notifications/initialized", "tools/list"}
        self.events.append({"direction": "client", "message": message})
        self.proc.stdin.write(json.dumps(message).encode() + b"\n")
        self.proc.stdin.flush()

    def request(self, method, params):
        self.next_id += 1
        wanted = self.next_id
        self.send({"jsonrpc": "2.0", "id": wanted, "method": method, "params": params})
        while True:
            remaining = self.until - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("MCP startup request exceeded 20 seconds")
            try:
                message = self.inbox.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError("MCP startup request exceeded 20 seconds") from None
            if message is None:
                raise RuntimeError("server exited before answering " + method)
            if isinstance(message, Exception):
                raise message
            assert message.get("jsonrpc") == "2.0", message
            if message.get("id") != wanted:
                continue
            if "error" in message:
                raise RuntimeError("MCP error for " + method + ": " + json.dumps(message["error"]))
            assert isinstance(message.get("result"), dict), message
            return message["result"]

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.thread.join(timeout=3)
        self.proc.stdout.close()


def prepare(version, index):
    item = next(item for item in index if item["package"] == "oracle-gateway" and item["version"] == version)
    wheel = ROOT / item["wheel"]
    assert sha(wheel) == item["sha256"], "wheel bytes changed"
    package_root = HERE / "artifacts" / version
    package_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            path = Path(member.filename)
            assert not path.is_absolute() and ".." not in path.parts
            assert member.file_size < 2_000_000
            if not member.is_dir():
                destination = package_root / path
                if destination.exists():
                    assert destination.read_bytes() == archive.read(member), "existing extracted bytes changed"
        archive.extractall(package_root)
    metadata = next(package_root.glob("*.dist-info/METADATA"))
    fields = {line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in metadata.read_text().splitlines()
              if line.startswith(("Name: ", "Version: "))}
    assert fields == {"Name": "aimarket-oracle-gateway", "Version": version}
    files = [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)} for path in sorted(package_root.rglob("*.py"))]
    return package_root, {"wheel": item["wheel"], "wheelSha256": item["sha256"], "metadata": fields, "files": files}


def replay(version, package_root, artifact):
    if (HERE / f"{version}-result.json").exists():
        raise RuntimeError("preserve existing replay receipts; choose a new evidence directory")
    cwd = HERE / "state" / version
    cwd.mkdir(parents=True, exist_ok=True)
    argv = [str(PYTHON), "-I", "-B", str(HERE / "guarded_launch.py"), "--package-root", str(package_root)]
    started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    client = None
    initialize = None
    tools = None
    error = None
    with (HERE / f"{version}-stderr.log").open("wb") as stderr:
        try:
            client = Client(argv, cwd, stderr)
            initialize = client.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                       "clientInfo": {"name": "oracle-startup-replay", "version": "1"}})
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = []
            cursor = None
            for _ in range(100):
                page = client.request("tools/list", {"cursor": cursor} if cursor else {})
                assert isinstance(page.get("tools"), list)
                tools.extend(page["tools"])
                assert len(tools) <= 2_000
                cursor = page.get("nextCursor")
                if cursor is None:
                    break
                assert isinstance(cursor, str) and cursor
            else:
                raise RuntimeError("tools/list pagination did not finish")
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            if client is not None:
                client.close()
    events = client.events if client else []
    if client is not None:
        (HERE / f"{version}-stdout.log").write_text("".join(client.raw_stdout), encoding="utf-8")
    result = {
        "version": version, "startedAt": started, "completedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact": artifact, "argv": argv, "cwd": str(cwd), "environmentNames": sorted(CLEAN_ENV),
        "guard": "Python audit hooks deny DNS, connections and child processes; not an OS sandbox",
        "processExitCode": client.proc.returncode if client else None,
        "initialize": initialize, "tools": tools, "toolCount": len(tools) if tools is not None else None,
        "toolCalls": 0, "error": error,
        "sourceHashes": {name: sha(HERE / name) for name in ("reproduce.py", "guarded_launch.py")},
    }
    save(HERE / f"{version}-wire.json", events)
    save(HERE / f"{version}-result.json", result)
    return result


def main():
    runtime = subprocess.run([str(PYTHON), "-I", "-B", "-c", "import importlib.metadata,json,platform; "
                              "print(json.dumps({'python':platform.python_version(),"
                              "'mcp':importlib.metadata.version('mcp'),'httpx':importlib.metadata.version('httpx'),"
                              "'pydantic':importlib.metadata.version('pydantic')}))"], env=CLEAN_ENV,
                             capture_output=True, text=True, timeout=15, check=True)
    profile = json.loads(runtime.stdout)
    assert profile["mcp"] == "1.30.0"
    profile["interpreter"] = str(PYTHON)
    profile["interpreterSha256"] = sha(PYTHON.resolve())
    save(HERE / "runtime.json", profile)
    index = json.loads((ORIGINAL / "artifact-index.json").read_text())
    results = {}
    for version in VERSIONS:
        package_root, artifact = prepare(version, index)
        results[version] = replay(version, package_root, artifact)
    old, current = (results[version] for version in VERSIONS)
    stderr = (HERE / "0.3.1-stderr.log").read_text()
    assert old["processExitCode"] == 1 and old["initialize"] is None and old["tools"] is None
    assert "NameError: name 'ValuesList' is not defined" in stderr
    assert "InvalidSignature" in stderr and "aggregate_values" in stderr
    assert current["processExitCode"] == 0 and current["error"] is None
    assert current["initialize"]["protocolVersion"] == "2025-06-18"
    assert current["initialize"]["serverInfo"] == {"name": "aimarket-oracle-gateway", "version": "0.3.2"}
    by_name = {tool["name"]: tool for tool in current["tools"]}
    assert len(by_name) == len(current["tools"]) == 36
    assert {"aggregate_values", "list_oracle_capabilities", "sortes_draw", "gauss_field", "aestus_seal",
            "betti_homology", "kantor_transport", "fourier_spectrum"} <= by_name.keys()
    values_schema = by_name["aggregate_values"]["inputSchema"]["properties"]["values"]
    assert values_schema["type"] == "array" and values_schema["minItems"] == 1
    assert all(isinstance(tool["inputSchema"], dict) for tool in current["tools"])
    verification = {"sameRuntimeProfile": True, "oldFailureReproduced": True, "currentStartupVerified": True,
                    "toolCalls": 0, "installations": 0, "networkRequests": 0,
                    "0.3.1": {"exitCode": old["processExitCode"], "cause": "ValuesList forward annotation is absent from function globals"},
                    "0.3.2": {"exitCode": current["processExitCode"], "protocol": current["initialize"]["protocolVersion"],
                              "serverVersion": current["initialize"]["serverInfo"]["version"], "tools": 36},
                    "files": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)}
                              for path in sorted(HERE.glob("*.json")) + sorted(HERE.glob("*.log")) + sorted(HERE.glob("*.py"))]}
    save(HERE / "verification.json", verification)
    print(json.dumps({key: verification[key] for key in ("oldFailureReproduced", "currentStartupVerified", "0.3.1", "0.3.2")}))


if __name__ == "__main__":
    main()
