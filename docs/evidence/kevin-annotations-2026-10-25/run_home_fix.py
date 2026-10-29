#!/usr/bin/env python3
"""Patch only the proven root-HOME guard defect into the existing isolated Linux run.

No dependency reinstall. Preserve the failed run; transfer only the changed path module
and its new child-process regression test, and retain both source snapshots with hashes.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import tarfile

import run_linux as runner


HERE = Path(__file__).resolve().parent
FILES = ("src/flow-guard-paths.ts", "test/flow-guard-home-paths.test.ts")


def with_home(command):
    result = list(command)
    at = result.index("--entrypoint")
    result[at:at] = ["-e", "HOME=/tmp/warden-home"]
    return result


def main():
    execution = HERE / "execution-home-fix.json"
    assert not execution.exists() and not (HERE / "results-home-fix").exists()
    original_bytes = (HERE / "execution.json").read_bytes()
    original = json.loads(original_bytes)
    manifest_bytes = (HERE / "input-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert runner.sha(manifest_bytes) == original["inputManifestSha256"]
    root = original["remoteTemp"]
    assert root.startswith(runner.PREFIX) and "/" not in root[len(runner.PREFIX):]
    assert original["image"] == runner.IMAGE and original["buildExitCode"] == 0
    assert original["testExitCode"] == 1
    frozen = {}
    for name in FILES:
        path = runner.WARDEN / name
        assert path.is_file() and not path.is_symlink()
        frozen[name] = path.read_bytes()
        frozen[name].decode("utf-8")
    delta = {name: {"sha256": runner.sha(data), "bytes": len(data)} for name, data in frozen.items()}
    runner.write_json(HERE / "home-fix-input-manifest.json", delta)
    archive = HERE / "home-fix-inputs.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in frozen.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), 0o644, 0
            tar.addfile(item, io.BytesIO(data))
    record = {
        "startedAt": runner.now(), "host": "admin-vps", "runtime": "runc", "image": runner.IMAGE,
        "remoteTemp": root, "originalExecution": "execution.json",
        "originalExecutionSha256": runner.sha(original_bytes),
        "originalInputManifestSha256": original["inputManifestSha256"],
        "deltaManifestSha256": runner.sha((HERE / "home-fix-input-manifest.json").read_bytes()),
        "deltaArchiveSha256": runner.sha(archive.read_bytes()), "deltaArchiveBytes": archive.stat().st_size,
        "deltaFiles": delta, "reinstalledDependencies": False,
        "orchestrationRunnerSha256": runner.sha(Path(__file__).read_bytes()),
        "helperRunnerSha256": runner.sha(Path(runner.__file__).read_bytes()),
        "sourceIdentity": "original frozen local candidate plus only the recorded root-HOME path fix and regression test",
        "network": "none for build, tests, probes", "realPaymentsUsed": False,
        "selectedTests": [*original["selectedTests"], "test/flow-guard-home-paths.test.ts"],
        "reason": "HOME=/ produces //.claude.json and //.claude/plugins under string concatenation; normalize with path.join",
        "state": "delta_frozen_not_transferred",
    }

    def save():
        runner.write_json(execution, record)

    save()
    try:
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(archive),
                        "admin-vps:" + root + "/home-fix-inputs.tar.gz"], check=True)
        prepare = r'''
import hashlib,json,os,pathlib,tarfile
root=pathlib.Path(ROOT);original=ORIGINAL;delta=DELTA;project=root/'study/project'
assert hashlib.sha256((root/'home-fix-inputs.tar.gz').read_bytes()).hexdigest()==SHA
for name,expected in original.items():
 if name.startswith('project/claude-plugin/scripts/flow-guard') and name.endswith('.mjs'):continue
 path=root/'study'/name
 assert hashlib.sha256(path.read_bytes()).hexdigest()==expected['sha256'],('Pre-patch frozen input changed',name)
assert not (project/'test/flow-guard-home-paths.test.ts').exists()
with tarfile.open(root/'home-fix-inputs.tar.gz','r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(delta) and {m.name for m in members}==set(delta)
 for member in members:
  parsed=pathlib.PurePosixPath(member.name)
  assert member.isfile() and not parsed.is_absolute() and '..' not in parsed.parts
  data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==delta[member.name]['sha256']
  assert len(data)==delta[member.name]['bytes']
  path=project/member.name;path.write_bytes(data);path.chmod(0o644);os.chown(path,65532,65532)
print(json.dumps({'verifiedOriginalInputs':len(original),'patchedFiles':delta}))
'''.replace("ROOT", repr(root)).replace("ORIGINAL", repr(manifest)).replace("DELTA", repr(delta)).replace(
            "SHA", repr(record["deltaArchiveSha256"]))
        record["remoteDeltaVerification"] = json.loads(runner.remote_python(prepare))
        record["state"] = "verified_delta_applied"
        save()
        build = with_home(original["buildCommand"])
        record["buildCommand"] = build
        record["buildExitCode"] = runner.stream(build, "build-home-fix.log")
        save()
        if record["buildExitCode"]:
            raise RuntimeError("Root-HOME candidate rebuild failed")
        record["artifactsAfterBuild"] = runner.collect_artifact_hashes(root, "artifacts-home-fix-after-build.json")
        tests = with_home(original["testCommand"])
        tests = ["--outputFile.json=/out/vitest-home-fix.json" if part.startswith("--outputFile.json=") else part for part in tests]
        tests += ["test/flow-guard-home-paths.test.ts"]
        record["testCommand"] = tests
        save()
        record["testExitCode"] = runner.stream(tests, "tests-home-fix.log")
        save()
        for name in ("baselineProbe", "candidateProbe"):
            command = with_home(original[name + "Command"])
            output_index = command.index("--out") + 1
            command[output_index] = command[output_index].replace(".json", "-home-fix.json")
            record[name + "Command"] = command
            record[name + "ExitCode"] = runner.stream(command, name + "-home-fix.log")
            save()
        record["artifactsAfterTests"] = runner.collect_artifact_hashes(root, "artifacts-home-fix-after-tests.json")
        verification = r'''
import hashlib,json,pathlib
root=pathlib.Path(ROOT);original=ORIGINAL;delta=DELTA;project=root/'study/project';out=root/'out'
checks={}
for name,expected in original.items():
 if name.startswith('project/claude-plugin/scripts/flow-guard') and name.endswith('.mjs'):continue
 if name=='project/src/flow-guard-paths.ts':continue
 path=root/'study'/name;actual={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 assert actual==expected,('Unrelated frozen input changed',name)
 checks[name]=actual
for name,expected in delta.items():
 path=project/name;actual={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 assert actual==expected,('Delta source changed',name)
 checks['project/'+name]=actual
before=json.loads((out/'artifacts-home-fix-after-build.json').read_text())
after=json.loads((out/'artifacts-home-fix-after-tests.json').read_text())
assert before==after,'Build outputs changed during tests'
baseline=json.loads((out/'baseline-home-fix.json').read_text());candidate=json.loads((out/'candidate-home-fix.json').read_text())
b={case['id']:case for case in baseline['cases']};c={case['id']:case for case in candidate['cases']}
assert set(b)==set(c) and len(b)==9
comparison={name:{'kind':c[name]['kind'],'baselineAdditionalPasses':b[name]['extraModelPassesRequested'],
 'candidateAdditionalPasses':c[name]['extraModelPassesRequested']} for name in b}
(out/'verified-source-home-fix.json').write_text(json.dumps(checks,indent=2)+'\n')
(out/'stop-comparison-home-fix.json').write_text(json.dumps({'cases':comparison,
 'interpretation':'Requested bounded extra model passes; no semantic protection or measured model latency claim.',
 'allUnrelatedInputsUnchanged':True,'compiledAndPluginArtifactsUnchangedDuringTests':True},indent=2)+'\n')
print(json.dumps({'verifiedInputs':len(checks),'stopProbeCases':len(comparison)}))
'''.replace("ROOT", repr(root)).replace("ORIGINAL", repr(manifest)).replace("DELTA", repr(delta))
        record["postRunVerification"] = json.loads(runner.remote_python(verification))
        if any(record.get(key) != 0 for key in ("testExitCode", "baselineProbeExitCode", "candidateProbeExitCode")):
            raise RuntimeError("Root-HOME regression run failed; preserve all evidence")
        record["state"] = "passed_not_cleaned"
    except BaseException as exc:
        record["state"] = "failed_not_cleaned"
        record["failure"] = runner.error_summary(exc)
        raise
    finally:
        record["finishedAt"] = runner.now()
        save()
        try:
            runner.download(root, "-home-fix", record)
        except BaseException as exc:
            record["outputDownloadError"] = runner.error_summary(exc)
            save()
            raise
        save()
        print(json.dumps({"state": record["state"], "remoteTemp": root,
                          "downloadedOutputs": record.get("downloadedOutputs", 0)}), flush=True)


if __name__ == "__main__":
    main()
