"""Capture WARDEN source-build definitions with a deny-network stdio launcher.

Replay sources are captured now; they do not reconstruct historical runtime observations.
No package installation, tools/call, pin operation or publication is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = HERE / ".work"
NODE = Path("/Users/alex/.nvm/versions/node/v22.22.1/bin/node")
PYTHON = ROOT / "histor/.venv/bin/python"
OLD_COMMIT = "fec7b195b8675ea5b74c18a7e65c0e3568c102a0"
SANDBOX_PROFILE = "(version 1)(allow default)(deny network*)"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def files_manifest(base: Path, suffix: str) -> list[dict[str, Any]]:
    return [{"path": str(path.relative_to(base)), "sha256": digest(path), "bytes": path.stat().st_size}
            for path in sorted(base.rglob("*")) if path.is_file() and str(path).endswith(suffix)]


def prepare() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "archive", "--format=tar", OLD_COMMIT, "warden/src", "warden/package.json", "warden/tsconfig.json"],
                             cwd=ROOT, capture_output=True, check=True).stdout
    old = WORK / "source-0.18.0"
    if old.exists():
        shutil.rmtree(old)
    old.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith("warden/"):
                raise ValueError("unexpected archive member")
            relative = Path(member.name).relative_to("warden")
            if ".." in relative.parts:
                raise ValueError("archive path escapes artifact root")
            target = old / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError("archive entry unreadable")
            target.write_bytes(stream.read())
    current = WORK / "source-0.22.1-local"
    if current.exists():
        shutil.rmtree(current)
    current.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "warden/src", current / "src", dirs_exist_ok=True)
    for name in ("package.json", "tsconfig.json"):
        shutil.copyfile(ROOT / "warden" / name, current / name)
    compiler = ROOT / "warden/node_modules/typescript/lib/tsc.js"
    node_version = subprocess.run([str(NODE), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    compiler_package = ROOT / "warden/node_modules/typescript"
    node_types = ROOT / "warden/node_modules/@types/node"
    manifest = {"node": {"path": str(NODE), "version": node_version, "sha256": digest(NODE)},
                "compiler": {"entry": str(compiler.relative_to(ROOT)), "sha256": digest(compiler),
                             "version": json.loads((compiler_package / "package.json").read_text())["version"],
                             "libraryJsFiles": files_manifest(compiler_package / "lib", ".js")},
                "nodeTypes": {"version": json.loads((node_types / "package.json").read_text())["version"],
                              "declarations": files_manifest(node_types, ".ts")},
                "oldGitCommit": OLD_COMMIT, "oldSourceArchiveSha256": digest_bytes(archive), "artifacts": {}}
    for label, artifact in (("source-0.18.0", old), ("source-0.22.1-local", current)):
        command = [str(NODE), str(compiler), "-p", str(artifact / "tsconfig.json"),
                   "--typeRoots", str(ROOT / "warden/node_modules/@types"), "--types", "node"]
        process = subprocess.run(command, cwd=artifact, capture_output=True, text=True, timeout=60, check=False)
        (HERE / f"build-{label}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise ValueError(f"{label} build failed")
        package = json.loads((artifact / "package.json").read_text())
        manifest["artifacts"][label] = {
            "path": str(artifact.relative_to(ROOT)), "name": package["name"], "declaredVersion": package["version"],
            "origin": "local Git source replay" if label == "source-0.18.0" else "current local working-tree source build",
            "sourceFiles": files_manifest(artifact / "src", ".ts"),
            "compiledFiles": files_manifest(artifact / "dist", ".js"),
            "packageJsonSha256": digest(artifact / "package.json"), "tsconfigSha256": digest(artifact / "tsconfig.json"),
            "buildCommand": command,
        }
    save(HERE / "build-provenance.json", manifest)
    print("Prepared isolated WARDEN 0.18.0 source replay and 0.22.1 local source build; no downloads")


def capture_one(label: str, artifact_name: str) -> None:
    sys.path.insert(0, str(ROOT / "histor"))
    from histor.toolcost_cli import _Stdio
    from histor.upgrade_brief import _validate_snapshot

    provenance = json.loads((HERE / "build-provenance.json").read_text())
    declared = provenance["artifacts"][artifact_name]["declaredVersion"]
    transcript: list[dict[str, Any]] = []

    class RecordingStdio(_Stdio):
        def send(self, msg):
            transcript.append({"direction": "request", "message": msg})
            return super().send(msg)

        def request(self, method, params, wait_s=None):
            try:
                result = super().request(method, params, wait_s)
                transcript.append({"direction": "response", "method": method, "result": result})
                return result
            except Exception as exc:
                transcript.append({"direction": "response", "method": method,
                                   "error": getattr(exc, "error", {"type": type(exc).__name__})})
                raise

    command = ["/usr/bin/sandbox-exec", "-p", SANDBOX_PROFILE, str(NODE), "dist/mcp-server.js"]
    client = RecordingStdio(command, time.monotonic() + 30)
    try:
        tools = client.tools()
        protocol = client.protocol_version
        info = client.server_info or {}
        assert protocol and info.get("version") == declared
        assert len(tools) == 9 and len({tool["name"] for tool in tools}) == 9
    finally:
        client.close()
    methods = [item["message"]["method"] for item in transcript if item["direction"] == "request"]
    assert "tools/call" not in methods and set(methods) <= {"server/discover", "initialize", "notifications/initialized", "tools/list"}
    document = {
        "format": "histor.upgrade-observation/v1", "targetId": "npm:@aimarket/warden", "status": "ok",
        "observedAt": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "packageVersion": declared, "serverName": info.get("name"), "serverVersion": info.get("version"),
        "protocol": protocol, "extrasCoverage": "observed",
        "launch": {
            "transport": "stdio", "command": ["node", "dist/mcp-server.js"], "workingDirectory": "artifact-root",
            "runtime": {"name": "node", "version": provenance["node"]["version"]},
            "environment": {"policy": "empty plus allowlist", "names": ["PATH", "WARDEN_STATE_DIR"],
                            "state": "fresh empty isolated directory", "pinMutations": "disabled"},
            "network": "denied by macOS sandbox-exec", "sandboxProfileSha256": digest_bytes(SANDBOX_PROFILE.encode()),
            "observer": "HISTOR _Stdio with complete tools/list, no tool calls",
        },
        "tools": tools,
    }
    _validate_snapshot(document)
    save(HERE / f"{label}.json", document)
    save(HERE / f"{label}-wire.json", {"methods": methods, "messages": transcript, "toolCalls": 0,
                                      "processExitCode": client.proc.returncode})
    state = Path(os.environ["WARDEN_STATE_DIR"])
    assert not list(state.rglob("*")), "discovery/list should not write pin state"
    save(HERE / f"{label}-provenance.json", {
        "snapshot": f"{label}.json", "sha256": digest(HERE / f"{label}.json"),
        "artifact": artifact_name, "buildProvenance": "build-provenance.json",
        "captureTimeIsCurrent": True, "historicalOriginalRecovered": False, "publishedPackageVerified": False,
        "protocol": protocol, "toolCount": len(tools), "toolsWithAnnotations": sum("annotations" in tool for tool in tools),
        "toolsWithTitle": sum("title" in tool for tool in tools), "toolCalls": 0,
        "stateDirectoryWasEmptyAfterCapture": True, "networkDeniedBySandbox": True,
    })
    print(json.dumps({"capture": label, "packageVersion": declared, "protocol": protocol, "tools": len(tools), "toolCalls": 0}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--one")
    parser.add_argument("--artifact")
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return
    if args.one:
        capture_one(args.one, args.artifact)
        return
    for label, artifact in (("replay-before", "source-0.18.0"), ("current-baseline", "source-0.22.1-local"),
                            ("current-recheck", "source-0.22.1-local")):
        state = WORK / "state" / label
        state.mkdir(parents=True, exist_ok=True)
        assert not list(state.rglob("*")), "state must be empty before capture"
        env = {"PATH": str(NODE.parent) + ":/usr/bin:/bin", "WARDEN_STATE_DIR": str(state)}
        process = subprocess.run([str(PYTHON), "-B", str(Path(__file__).resolve()), "--one", label, "--artifact", artifact],
                                 cwd=WORK / artifact, env=env, capture_output=True, text=True, timeout=45, check=False)
        (HERE / f"{label}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise ValueError(f"{label}: capture failed: {process.stderr}")
        print(process.stdout.strip())


if __name__ == "__main__":
    main()
