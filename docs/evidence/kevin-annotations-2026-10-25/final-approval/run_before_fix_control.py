#!/usr/bin/env python3
"""A separate Linux control: current race tests and fixtures, exact previous wrap.ts.

This deliberately expects three failing parameterized cases from two test definitions.
It does not modify the final candidate tree or reinstall dependencies.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import tarfile

import run_linux as runner

HERE = Path(__file__).resolve().parent
PATTERN = "never reuses an old tools/list already in flight when approval arrives|rechecks shared credential/taint state after annotation approval"


def main():
    execution = HERE / "execution-before-fix-control.json"
    assert not execution.exists() and not (HERE / "results-before-fix-control").exists()
    main_bytes = (HERE / "execution.json").read_bytes()
    final = json.loads(main_bytes)
    assert final["state"] == "passed_not_cleaned" and final["testExitCode"] == 0
    root = final["remoteTemp"]
    assert root.startswith(runner.PREFIX) and "/" not in root[len(runner.PREFIX):]
    previous_manifest = json.loads((HERE.parent / "input-manifest.json").read_text())
    old_meta = previous_manifest["project/src/wrap.ts"]
    with tarfile.open(HERE.parent / "inputs.tar.gz", "r:gz") as tar:
        old = tar.extractfile("project/src/wrap.ts").read()
    assert {"sha256": runner.sha(old), "bytes": len(old)} == old_meta
    previous_wrap = HERE / "before-fix-wrap.ts"
    assert not previous_wrap.exists()
    previous_wrap.write_bytes(old)
    archive = HERE / "before-fix-control-input.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        item = tarfile.TarInfo("wrap.ts")
        item.size, item.mode, item.mtime = len(old), 0o644, 0
        tar.addfile(item, io.BytesIO(old))
    record = {
        "startedAt": runner.now(), "remoteTemp": root, "host": "admin-vps", "image": runner.IMAGE,
        "runtime": "runc", "network": "none", "reinstalledDependencies": False,
        "finalExecutionSha256": runner.sha(main_bytes), "beforeFixWrap": old_meta,
        "previousSource": "parent inputs.tar.gz:project/src/wrap.ts (the pre-race-fix candidate)",
        "currentTestsAndFixtures": "identical to final candidate, final-approval/input-manifest.json",
        "testNamePattern": PATTERN, "expectedFailedCases": 3, "testDefinitions": 2,
        "inputArchiveSha256": runner.sha(archive.read_bytes()), "inputArchiveBytes": archive.stat().st_size,
        "state": "control_prepared_not_transferred",
    }

    def save():
        runner.write_json(execution, record)

    save()
    try:
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(archive),
                        "admin-vps:" + root + "/before-fix-control-input.tar.gz"], check=True)
        prepare = r'''
import hashlib,json,os,pathlib,shutil,tarfile
root=pathlib.Path(ROOT);old_meta=OLD_META
project=root/'study/project';control=root/'before-fix-control'
assert not control.exists()
assert hashlib.sha256((root/'before-fix-control-input.tar.gz').read_bytes()).hexdigest()==ARCHIVE_SHA
shutil.copytree(project,control,ignore=shutil.ignore_patterns('node_modules','dist'))
with tarfile.open(root/'before-fix-control-input.tar.gz','r:gz') as tar:
 entries=tar.getmembers();assert len(entries)==1 and entries[0].isfile() and entries[0].name=='wrap.ts'
 data=tar.extractfile(entries[0]).read()
 assert {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}==old_meta
 (control/'src/wrap.ts').write_bytes(data)
checks={}
for path in project.rglob('*'):
 if not path.is_file() or 'node_modules' in path.relative_to(project).parts or 'dist' in path.relative_to(project).parts:continue
 name=path.relative_to(project).as_posix();other=control/name
 assert other.is_file() and not other.is_symlink()
 expected=old_meta if name=='src/wrap.ts' else {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 actual={'sha256':hashlib.sha256(other.read_bytes()).hexdigest(),'bytes':other.stat().st_size}
 assert actual==expected,name
 checks[name]=actual
for directory,_,files in os.walk(control):
 os.chown(directory,65532,65532);os.chmod(directory,0o755)
 for name in files:os.chown(pathlib.Path(directory)/name,65532,65532)
(root/'out/before-fix-control-source-manifest.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({'controlFiles':len(checks),'onlySourceDifference':'src/wrap.ts','oldWrap':old_meta}))
'''.replace("ROOT", repr(root)).replace("OLD_META", repr(old_meta)).replace("ARCHIVE_SHA", repr(record["inputArchiveSha256"]))
        record["remoteSourceVerification"] = json.loads(runner.remote_python(prepare))
        save()

        def control(command):
            result = list(command)
            result = [part.replace(root + "/study/project:/work:rw", root + "/before-fix-control:/work:rw") for part in result]
            at = result.index("--workdir")
            result[at:at] = ["-v", root + "/study/project/node_modules:/work/node_modules:rw"]
            return result

        build = control(final["buildCommand"])
        record["buildCommand"] = build
        record["buildExitCode"] = runner.stream(build, "before-fix-control-build.log")
        save()
        if record["buildExitCode"]:
            raise RuntimeError("Before-fix control did not compile; cannot interpret the test comparison")
        original_tests = control(final["testCommand"])
        image_index = original_tests.index(runner.IMAGE)
        tests = original_tests[:image_index + 1] + [
            "node_modules/vitest/vitest.mjs", "run", "test/annotation-review.test.ts", "-t", PATTERN,
            "--maxWorkers=1", "--no-file-parallelism", "--reporter=default", "--reporter=json",
            "--outputFile.json=/out/before-fix-control-tests.json",
        ]
        record["testCommand"] = tests
        record["testExitCode"] = runner.stream(tests, "before-fix-control-tests.log")
        save()
        result = runner.remote_python(r'''
import hashlib,json,pathlib
root=pathlib.Path(ROOT);out=root/'out';result=json.loads((out/'before-fix-control-tests.json').read_text())
failed=[{'name':case['fullName'],'failureMessages':case.get('failureMessages',[])}
 for file in result['testResults'] for case in file['assertionResults'] if case['status']=='failed']
assert len(failed)==3 and result['numFailedTests']==3 and result['numPassedTests']==0
assert sum('never reuses an old tools/list' in case['name'] for case in failed)==1
assert sum('rechecks shared credential/taint state' in case['name'] for case in failed)==2
artifacts={path.relative_to(root/'before-fix-control').as_posix():{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 for path in sorted((root/'before-fix-control/dist').rglob('*')) if path.is_file()}
(out/'before-fix-control-artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
print(json.dumps({'expectedRegressionsReproduced':True,'failedCases':failed,'compiledArtifacts':len(artifacts)}))
'''.replace("ROOT", repr(root)))
        record["regressionComparison"] = json.loads(result)
        assert record["testExitCode"] == 1
        record["state"] = "expected_regressions_reproduced_not_cleaned"
    except BaseException as exc:
        record["state"] = "control_failed_not_cleaned"
        record["failure"] = runner.error_summary(exc)
        raise
    finally:
        record["finishedAt"] = runner.now()
        save()
        try:
            runner.download(root, "-before-fix-control", record)
        except BaseException as exc:
            record["outputDownloadError"] = runner.error_summary(exc)
            save()
            raise
        save()
        print(json.dumps({"state": record["state"], "remoteTemp": root,
                          "downloadedOutputs": record.get("downloadedOutputs", 0)}), flush=True)


if __name__ == "__main__":
    main()
