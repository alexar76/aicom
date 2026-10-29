#!/usr/bin/env python3
"""Build and test exact local WARDEN sources on Linux; compare the Stop hook with 0.21.0.

Only lockfile development-dependency preparation has network access. The build,
selected tests and probes execute our code with synthetic MCP fixtures, no external
MCP implementation, model inference, real payment or production service changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tarfile


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
WARDEN = WORKSPACE / "warden"
IMAGE = "sha256:e1b65057659c168cb8510100daeca2f95d6e3f7ec081ed1b98f217591359b7a3"
# The public own artifact is intentionally fixed, not rebuilt from a dirty checkout.
BASELINE_SHA = "5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1"
BASELINE = HERE.parent / "auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "admin-vps"]
PREFIX = "/tmp/kevin-annotations-20261025."
TESTS = [
    "test/annotation-review.test.ts", "test/flow-guard-answer-review.test.ts",
    "test/wrap.test.ts", "test/flow-guard.test.ts", "test/flow-guard-gaps.test.ts",
    "test/flow-guard-credential-boundary.test.ts", "test/toxic-flow.test.ts", "test/result-screen.test.ts",
    "test/flow-guard-home-paths.test.ts",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)])


def remote_python(script):
    return subprocess.check_output(SSH + ["python3 -"], input=script.encode("utf-8"))


def error_summary(exc):
    if isinstance(exc, subprocess.CalledProcessError):
        return {"type": type(exc).__name__, "exitCode": exc.returncode,
                "message": "Remote subprocess failed; consult the saved phase command and log"}
    return {"type": type(exc).__name__, "message": str(exc)[:2000]}


def stream(args, filename):
    assert not (HERE / filename).exists(), filename
    with (HERE / filename).open("wb") as handle:
        child = subprocess.Popen(SSH + [shlex.join(args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in child.stdout:
            handle.write(line)
            handle.flush()
            print(line.decode(errors="replace")[:1800].rstrip(), flush=True)
        return child.wait()


def freeze():
    """Hash and archive the same in-memory bytes even if another chat edits the checkout."""
    frozen = {}

    def add(path, name=None, binary=False):
        path = Path(path)
        assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(WORKSPACE), path
        name = name or "project/" + path.relative_to(WARDEN).as_posix()
        parsed = PurePosixPath(name)
        assert not parsed.is_absolute() and ".." not in parsed.parts
        assert not any(part.startswith(".") and part != ".claude-plugin" for part in parsed.parts), name
        content = path.read_bytes()
        if not binary:
            content.decode("utf-8")
            assert b"\x00" not in content
        if name in frozen:
            assert frozen[name] == content
        frozen[name] = content
        return content

    for path in sorted((WARDEN / "src").rglob("*.ts")):
        add(path)
    initial = [*TESTS, "test/setup.ts", "test/global-setup.ts", "vitest.config.ts"]
    # A conservative text scan resolves static relative imports and literal dynamic
    # imports; all own source modules are already included. It executes no TS on Mac.
    pending = [WARDEN / name for name in initial]
    visited = set()
    specifier = re.compile(r"^[ \t]*(?:import|export)\s+(?:[^;]*?\s+from\s*)?['\"]([^'\"]+)['\"]", re.MULTILINE)
    while pending:
        path = pending.pop().resolve()
        if path in visited:
            continue
        visited.add(path)
        content = add(path).decode("utf-8")
        for match in specifier.finditer(content):
            if not match[1].startswith("."):
                continue
            target = (path.parent / match[1]).resolve()
            options = [target, target.with_suffix(".ts"), target / "index.ts"]
            found = next((candidate for candidate in options if candidate.is_file()), None)
            assert found is not None, (path, match[1])
            assert found.is_relative_to(WARDEN), found
            if not found.is_relative_to(WARDEN / "src"):
                pending.append(found)
    for name in ("package.json", "package-lock.json", "tsconfig.json", "scripts/sync-flow-guard.mjs",
                 "examples/atomic-screen-server.mjs"):
        add(WARDEN / name)
    for path in sorted((WARDEN / "test/fixtures").rglob("*.mjs")):
        add(path)
    for path in sorted((WARDEN / "claude-plugin").rglob("*")):
        if path.is_file() and path.suffix in {".mjs", ".json"}:
            add(path)
    add(HERE / "probe_stop_candidate.mjs", "research/probe_stop_candidate.mjs")
    add(Path(__file__), "research/run_linux.py")
    baseline = add(BASELINE, "baseline/warden-0.21.0.tgz", binary=True)
    assert sha(baseline) == BASELINE_SHA, "Unexpected public WARDEN 0.21.0 artifact"
    manifest = {name: {"sha256": sha(content), "bytes": len(content)} for name, content in sorted(frozen.items())}
    manifest_path = HERE / "input-manifest.json"
    archive = HERE / "inputs.tar.gz"
    assert not manifest_path.exists() and not archive.exists()
    write_json(manifest_path, manifest)
    with tarfile.open(archive, "w:gz") as tar:
        for name, content in sorted(frozen.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(content), 0o644, 0
            tar.addfile(entry, io.BytesIO(content))
    return manifest, archive


def collect_artifact_hashes(root, name):
    script = r'''
import hashlib,json,pathlib
root=pathlib.Path(ROOT);project=root/'study/project'
result={}
for base in (project/'dist',project/'claude-plugin/scripts'):
 for path in sorted(base.rglob('*')) if base.exists() else []:
  if path.is_file():
   assert not path.is_symlink()
   result[path.relative_to(project).as_posix()]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
(root/'out'/NAME).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'manifest':NAME,'artifacts':len(result)}))
'''.replace("ROOT", repr(root)).replace("NAME", repr(name))
    return json.loads(remote_python(script))


def download(root, suffix, record):
    script = r'''
import hashlib,io,json,pathlib,sys,tarfile
root=pathlib.Path(ROOT);out=root/'out';buffer=io.BytesIO();manifest={}
with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
 for path in sorted(out.rglob('*')) if out.exists() else []:
  if not path.is_file():continue
  assert not path.is_symlink() and path.suffix in {'.json','.xml','.txt','.log'}
  data=path.read_bytes();name=path.relative_to(out).as_posix()
  manifest[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o644;tar.addfile(item,io.BytesIO(data))
 data=(json.dumps(manifest,indent=2)+'\n').encode();item=tarfile.TarInfo('_remote-manifest.json')
 item.size=len(data);item.mode=0o644;tar.addfile(item,io.BytesIO(data))
sys.stdout.buffer.write(buffer.getvalue())
'''.replace("ROOT", repr(root))
    payload = remote_python(script)
    archive = HERE / ("outputs" + suffix + ".tar.gz")
    output = HERE / ("results" + suffix)
    assert not archive.exists() and not output.exists()
    archive.write_bytes(payload)
    output.mkdir()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        entries = tar.getmembers()
        assert len({entry.name for entry in entries}) == len(entries)
        for entry in entries:
            parsed = PurePosixPath(entry.name)
            assert entry.isfile() and not parsed.is_absolute() and ".." not in parsed.parts
            target = output.joinpath(*parsed.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(entry).read())
    expected = json.loads((output / "_remote-manifest.json").read_text())
    actual = {path.relative_to(output).as_posix(): {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
              for path in sorted(output.rglob("*")) if path.is_file() and path.name != "_remote-manifest.json"}
    assert actual == expected
    write_json(HERE / ("output-manifest" + suffix + ".json"), actual)
    record.update({"downloadedOutputs": len(actual), "outputArchiveSha256": sha(payload)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", metavar="NAME", help="Use original frozen input bytes in a new temp root; keep prior results")
    args = parser.parse_args()
    assert args.retry is None or re.fullmatch(r"retry[1-9][0-9]*", args.retry)
    suffix = "-" + args.retry if args.retry else ""
    execution = HERE / ("execution" + suffix + ".json")
    assert not execution.exists() and not (HERE / ("results" + suffix)).exists()
    original = None
    if args.retry:
        original_path = HERE / "execution.json"
        original = json.loads(original_path.read_text())
        manifest_bytes = (HERE / "input-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        archive = HERE / "inputs.tar.gz"
        assert sha(manifest_bytes) == original["inputManifestSha256"]
        assert sha(archive.read_bytes()) == original["inputArchiveSha256"]
        assert original["image"] == IMAGE and original["publishedBaselineSha256"] == BASELINE_SHA
    else:
        manifest, archive = freeze()
    root = remote(["mktemp", "-d", PREFIX + "XXXXXX"]).decode().strip()
    assert root.startswith(PREFIX) and "/" not in root[len(PREFIX):]
    record = {
        "startedAt": now(), "host": "admin-vps", "runtime": "runc", "image": IMAGE, "remoteTemp": root,
        "sourceIdentity": "exact frozen local unreleased WARDEN candidate; package version string is not a release claim",
        "publishedBaselineVersion": "0.21.0", "publishedBaselineSha256": BASELINE_SHA,
        "inputFiles": len(manifest), "inputArchiveBytes": archive.stat().st_size,
        "inputArchiveSha256": sha(archive.read_bytes()),
        "inputManifestSha256": sha((HERE / "input-manifest.json").read_bytes()),
        "workspaceHeadAtFreeze": original["workspaceHeadAtFreeze"] if original else subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
        "dependencyPreparationNetwork": "bridge, npm ci --ignore-scripts with frozen package-lock.json",
        "buildTestsProbesNetwork": "none", "externalMcpCodeExecuted": False, "modelInferenceUsed": False,
        "realPaymentsUsed": False, "selectedTests": original["selectedTests"] if original else TESTS,
        "state": "frozen_not_transferred",
    }
    if original:
        record.update({"retryOf": "execution.json", "originalExecutionSha256": sha((HERE / "execution.json").read_bytes()),
                       "orchestrationRunnerSha256": sha(Path(__file__).read_bytes())})
    write_json(execution, record)

    def save():
        write_json(execution, record)

    try:
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(archive),
                        "admin-vps:" + root + "/inputs.tar.gz"], check=True)
        prepare = r'''
import hashlib,json,os,pathlib,tarfile
root=pathlib.Path(ROOT);manifest=MANIFEST;archive_sha=ARCHIVE_SHA
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==archive_sha
study=root/'study';study.mkdir();out=root/'out';out.mkdir();baseline=root/'baseline';baseline.mkdir()
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(manifest) and {m.name for m in members}==set(manifest)
 for member in members:
  parsed=pathlib.PurePosixPath(member.name)
  assert member.isfile() and not parsed.is_absolute() and '..' not in parsed.parts and member.name in manifest
  data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==manifest[member.name]['sha256']
  assert len(data)==manifest[member.name]['bytes']
  path=study/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o644)
assert hashlib.sha256((study/'baseline/warden-0.21.0.tgz').read_bytes()).hexdigest()==BASELINE_SHA
with tarfile.open(study/'baseline/warden-0.21.0.tgz','r:gz') as tar:
 for member in tar.getmembers():
  parsed=pathlib.PurePosixPath(member.name)
  assert not parsed.is_absolute() and '..' not in parsed.parts and parsed.parts[0]=='package'
  if member.isdir():continue
  assert member.isfile()
  path=baseline.joinpath(*parsed.parts);path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(tar.extractfile(member).read());path.chmod(0o644)
os.chmod(root,0o755);os.chown(out,65532,65532)
for directory,_,files in os.walk(study/'project'):
 os.chown(directory,65532,65532);os.chmod(directory,0o755)
 for filename in files:os.chown(pathlib.Path(directory)/filename,65532,65532)
print(json.dumps({'verifiedFiles':len(manifest),'baselineVersion':json.loads((baseline/'package/package.json').read_text())['version']}))
'''.replace("ROOT", repr(root)).replace("MANIFEST", repr(manifest)).replace(
            "ARCHIVE_SHA", repr(record["inputArchiveSha256"])).replace("BASELINE_SHA", repr(BASELINE_SHA))
        record["remoteInputVerification"] = json.loads(remote_python(prepare))
        record["state"] = "verified_remote_inputs"
        save()

        def container(network, entrypoint="node"):
            return ["docker", "run", "--rm", "--runtime", "runc", "--read-only", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--memory", "768m", "--memory-swap", "768m",
                    "--cpus", "1", "--pids-limit", "128", "--network", network,
                    "--tmpfs", "/tmp:rw,nosuid,noexec,size=256m", "--user", "65532:65532",
                    "-v", root + "/study/project:/work:rw", "-v", root + "/study/research:/research:ro",
                    "-v", root + "/baseline:/baseline:ro", "-v", root + "/out:/out:rw",
                    "--workdir", "/work", "-e", "WARDEN_STATE_DIR=/tmp/warden-state",
                    "-e", "HOME=/tmp/warden-home",
                    "-e", "npm_config_cache=/tmp/npm-cache", "--entrypoint", entrypoint, IMAGE]

        setup = container("bridge", "npm") + ["ci", "--ignore-scripts", "--no-audit", "--no-fund", "--cache", "/tmp/npm-cache"]
        record["dependencyPreparationCommand"] = setup
        save()
        record["dependencyPreparationExitCode"] = stream(setup, "dependency-preparation" + suffix + ".log")
        save()
        if record["dependencyPreparationExitCode"]:
            raise RuntimeError("Lockfile dependency preparation failed")
        build = container("none", "npm") + ["run", "build"]
        record["buildCommand"] = build
        save()
        record["buildExitCode"] = stream(build, "build" + suffix + ".log")
        save()
        if record["buildExitCode"]:
            raise RuntimeError("Local candidate build failed")
        record["artifactsAfterBuild"] = collect_artifact_hashes(root, "artifacts-after-build.json")

        runtime_js = """import fs from 'node:fs';import cp from 'node:child_process';
fs.writeFileSync('/out/runtime.json',JSON.stringify({platform:process.platform,node:process.version,
versions:process.versions,npm:cp.execFileSync('npm',['--version'],{encoding:'utf8'}).trim(),
typescript:JSON.parse(fs.readFileSync('node_modules/typescript/package.json')).version,
vitest:JSON.parse(fs.readFileSync('node_modules/vitest/package.json')).version,
sourcePackageVersionString:JSON.parse(fs.readFileSync('package.json')).version,
candidateIsPublishedArtifact:false},null,2)+'\\n');"""
        metadata = container("none") + ["--input-type=module", "-e", runtime_js]
        record["runtimeMetadataCommand"] = metadata
        record["runtimeMetadataExitCode"] = stream(metadata, "runtime" + suffix + ".log")
        if record["runtimeMetadataExitCode"]:
            raise RuntimeError("Runtime metadata failed")

        tests = container("none") + ["node_modules/vitest/vitest.mjs", "run", *record["selectedTests"],
                                     "--maxWorkers=1", "--no-file-parallelism", "--reporter=default", "--reporter=json",
                                     "--outputFile.json=/out/vitest.json"]
        record["testCommand"] = tests
        save()
        record["testExitCode"] = stream(tests, "tests" + suffix + ".log")
        save()
        for label, artifact in (("published-0.21.0", "/baseline/package"), ("local-unreleased-candidate", "/work")):
            filename = "baseline.json" if artifact.startswith("/baseline") else "candidate.json"
            command = container("none") + ["/research/probe_stop_candidate.mjs", "--warden-root", artifact,
                                          "--label", label, "--out", "/out/" + filename]
            key = "baselineProbe" if filename == "baseline.json" else "candidateProbe"
            record[key + "Command"] = command
            save()
            record[key + "ExitCode"] = stream(command, key + suffix + ".log")
            save()
        record["artifactsAfterTests"] = collect_artifact_hashes(root, "artifacts-after-tests.json")

        verification = r'''
import hashlib,json,pathlib
root=pathlib.Path(ROOT);manifest=MANIFEST;study=root/'study';out=root/'out'
source={};generated=[]
for name,expected in manifest.items():
 path=study/name
 actual={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 if name.startswith('project/claude-plugin/scripts/flow-guard') and name.endswith('.mjs'):
  generated.append(name)
 else:
  assert actual==expected, ('An input changed during the run',name)
  source[name]=actual
(out/'verified-source-manifest.json').write_text(json.dumps({'unchangedInputs':source,'buildGeneratedPluginFiles':generated},indent=2)+'\n')
before=json.loads((out/'artifacts-after-build.json').read_text());after=json.loads((out/'artifacts-after-tests.json').read_text())
assert before==after,'Compiled artifacts or generated plugin changed during tests'
if (out/'baseline.json').exists() and (out/'candidate.json').exists():
 baseline=json.loads((out/'baseline.json').read_text());candidate=json.loads((out/'candidate.json').read_text())
 b={case['id']:case for case in baseline['cases']};c={case['id']:case for case in candidate['cases']}
 assert set(b)==set(c) and len(b)==9
 comparison={name:{'kind':c[name]['kind'],'baselineAdditionalPasses':b[name]['extraModelPassesRequested'],
  'candidateAdditionalPasses':c[name]['extraModelPassesRequested'],
  'baselineHookDurationMs':b[name]['observedHookDurationMs'],'candidateHookDurationMs':c[name]['observedHookDurationMs']}
  for name in b}
 (out/'stop-comparison.json').write_text(json.dumps({'cases':comparison,
  'interpretation':'Deterministic copied-window check; extra model passes requested, not measured model latency or semantic attack prevention.',
  'sourceInputsUnchanged':True,'compiledAndPluginArtifactsUnchangedDuringTests':True},indent=2)+'\n')
print(json.dumps({'verifiedUnchangedInputs':len(source),'generatedPluginInputs':len(generated)}))
'''.replace("ROOT", repr(root)).replace("MANIFEST", repr(manifest))
        record["postRunInputVerification"] = json.loads(remote_python(verification))
        if any(record.get(key) != 0 for key in ("testExitCode", "baselineProbeExitCode", "candidateProbeExitCode")):
            raise RuntimeError("Tests or a Stop probe failed; preserve the complete run for investigation")
        record["state"] = "passed_not_cleaned"
    except BaseException as exc:
        record["state"] = "failed_not_cleaned"
        record["failure"] = error_summary(exc)
        raise
    finally:
        record["finishedAt"] = now()
        save()
        try:
            download(root, suffix, record)
        except BaseException as exc:
            record["outputDownloadError"] = error_summary(exc)
            save()
            raise
        save()
        print(json.dumps({"state": record["state"], "remoteTemp": root,
                          "downloadedOutputs": record.get("downloadedOutputs", 0)}), flush=True)


if __name__ == "__main__":
    main()
