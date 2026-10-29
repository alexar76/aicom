#!/usr/bin/env python3
"""Freeze own current Hub sources, then test synthetic money on an isolated Linux host.

This runner is not a package-release reproduction. It records every transferred source
byte, including local changes. Only wheel preparation has a network; the application,
tests, ledger trace, and dependency inspection run with Docker --network none.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tarfile


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
HUB = WORKSPACE / "aimarket-hub"
IMAGE = "sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "admin-vps"]
REMOTE_PREFIX = "/tmp/micky-main-integration-20261025."
TEXT_SUFFIXES = {".py", ".json", ".html", ".css", ".txt"}
TESTS = [
    "tests/test_micky_credit_lifecycle.py",
    "tests/test_micky_mcp_payment_flow.py",
    "tests/test_micky_expiry_recovery.py",
    "tests/test_credits_rail.py",
    "tests/test_credits_invoke.py",
    "tests/test_credit_hold_recovery.py",
    "tests/test_mcp_api_key.py",
    "tests/test_mandates.py::TestLimits",
    "tests/test_mandates.py::TestLimitsCannotBeDodged",
    "tests/test_channels.py::TestPayoutObligations",
    "tests/test_channels.py::TestOrphanedHoldReaper",
]


PREPARE_DEPENDENCIES = r'''
from collections import defaultdict
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib
from pip._vendor.packaging.markers import Marker

assert sys.version_info[:2] == (3, 11), sys.version
assert platform.system() == 'Linux'
lock = tomllib.loads(Path('/work/uv.lock').read_text())
packages = defaultdict(list)
for package in lock['package']:
    packages[package['name']].append(package)
root = [p for p in packages['aimarket-hub'] if p.get('source', {}).get('editable') == '.']
assert len(root) == 1
root = root[0]
pending = list(root.get('dependencies', [])) + [
    {'name': 'pytest'}, {'name': 'pytest-asyncio'}, {'name': 'pytest-httpx'},
]
selected = {}
active_extras = defaultdict(set)
walked = {}

def applies(edge, extras):
    marker = edge.get('marker')
    return not marker or any(Marker(marker).evaluate({'extra': extra}) for extra in {'', *extras})

while pending:
    edge = pending.pop()
    name = edge['name']
    assert name != 'aimarket-hub', 'Never install a second Hub over current source'
    choices = packages[name]
    if edge.get('version'):
        choices = [p for p in choices if p['version'] == edge['version']]
    assert len(choices) == 1, (name, [p['version'] for p in choices])
    package = choices[0]
    assert package.get('source', {}).get('registry') == 'https://pypi.org/simple', package['source']
    active_extras[name].update(edge.get('extra', []))
    selected[name] = package
    extras = frozenset(active_extras[name])
    if name in walked and walked[name] == extras:
        continue
    walked[name] = extras
    dependencies = list(package.get('dependencies', []))
    for extra in extras:
        dependencies.extend(package.get('optional-dependencies', {}).get(extra, []))
    pending.extend(d for d in dependencies if applies(d, extras))

lines = []
resolved = []
for name, package in sorted(selected.items()):
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', name)
    assert re.fullmatch(r'[A-Za-z0-9_.+!-]+', package['version'])
    hashes = sorted({wheel['hash'] for wheel in package.get('wheels', [])})
    assert hashes, (name, 'No wheel hash in lockfile; refusing an sdist build')
    assert all(re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in hashes)
    lines.append(name + '==' + package['version'] + ' ' + ' '.join('--hash=' + value for value in hashes))
    resolved.append({'name': name, 'version': package['version'],
                     'active_extras': sorted(active_extras[name]), 'wheel_hashes': hashes})
Path('/out/requirements.lock.txt').write_text('\n'.join(lines) + '\n')
Path('/out/dependency-selection.json').write_text(json.dumps({
    'source': '/work/uv.lock', 'root': 'aimarket-hub runtime plus dev test dependencies',
    'root_source_version_string': root['version'], 'installed_current_hub': False,
    'python': sys.version, 'platform': platform.platform(),
    'packages': resolved,
}, indent=2) + '\n')
subprocess.run([
    sys.executable, '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
    '--index-url', 'https://pypi.org/simple', '--only-binary=:all:', '--no-deps',
    '--require-hashes', '--no-cache-dir', '--target', '/deps', '-r', '/out/requirements.lock.txt',
], check=True)
print(json.dumps({'selected_packages': len(resolved), 'status': 'installed_locked_wheels'}))
'''


RUNTIME_METADATA = r'''
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
installed = sorted(({'name': d.metadata['Name'], 'version': d.version}
                    for d in importlib.metadata.distributions(path=['/deps'])), key=lambda p: p['name'].lower())
freeze = subprocess.check_output([sys.executable, '-m', 'pip', '--isolated',
                                  '--disable-pip-version-check', 'freeze', '--path', '/deps'], text=True)
Path('/out/pip-freeze.txt').write_text(freeze)
Path('/out/runtime.json').write_text(json.dumps({
    'python': sys.version, 'platform': platform.platform(), 'sqlite': sqlite3.sqlite_version,
    'dependency_packages': installed, 'hub_source_sha256': {
        str(p.relative_to('/work')): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path('/work/aimarket_hub').rglob('*.py'))},
    'current_source_not_published_wheel': True,
}, indent=2) + '\n')
'''


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)])


def remote_python(script):
    # Feed program text on stdin: shell argv length is much smaller than a manifest.
    return subprocess.check_output(SSH + ["python3 -"], input=script.encode("utf-8"))


def concise_error(exc):
    if isinstance(exc, subprocess.CalledProcessError):
        return {"type": type(exc).__name__, "exitCode": exc.returncode,
                "message": "Remote subprocess failed; command and detailed output are in the phase log"}
    return {"type": type(exc).__name__, "message": str(exc)[:2000]}


def run_logged(args, filename):
    with (HERE / filename).open("wb") as log:
        child = subprocess.Popen(SSH + [shlex.join(args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in child.stdout:
            log.write(line)
            log.flush()
            print(line.decode(errors="replace").rstrip(), flush=True)
        return child.wait()


def freeze_inputs():
    """Compose the historical 193-file input set with exact current application bytes.

    All four research helpers remain byte-identical to the historical run. Only
    application/config/test files come from the current workspace, read once.
    """
    historical = HERE.parent
    previous_manifest_bytes = (historical / "input-manifest.json").read_bytes()
    previous_manifest = json.loads(previous_manifest_bytes)
    previous_execution = json.loads((historical / "execution.json").read_text())
    previous_archive_bytes = (historical / "inputs.tar.gz").read_bytes()
    assert sha_bytes(previous_manifest_bytes) == previous_execution["inputManifestSha256"]
    assert sha_bytes(previous_archive_bytes) == previous_execution["inputArchiveSha256"]
    inputs = {}
    changes = {}
    with tarfile.open(fileobj=io.BytesIO(previous_archive_bytes), mode="r:gz") as tar:
        entries = tar.getmembers()
        assert len(entries) == len(previous_manifest) == 193
        assert {entry.name for entry in entries} == set(previous_manifest)
        for entry in entries:
            assert entry.isfile()
            parsed = PurePosixPath(entry.name)
            assert not parsed.is_absolute() and ".." not in parsed.parts
            old = tar.extractfile(entry).read()
            assert {"sha256": sha_bytes(old), "bytes": len(old)} == previous_manifest[entry.name]
            if entry.name.startswith("_experiment/"):
                content = old
            else:
                source = HUB / entry.name
                assert source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(HUB)
                content = source.read_bytes()
                content.decode("utf-8")
                assert b"\x00" not in content
            inputs[entry.name] = content
            if content != old:
                changes[entry.name] = {"before": previous_manifest[entry.name],
                                       "current": {"sha256": sha_bytes(content), "bytes": len(content)}}
    expected_modules = {name for name in inputs if name.startswith("aimarket_hub/")}
    actual_modules = {path.relative_to(HUB).as_posix() for path in (HUB / "aimarket_hub").rglob("*")
                      if path.is_file() and path.suffix in TEXT_SUFFIXES}
    assert expected_modules == actual_modules, "A new application module needs inclusion in the integration input set"
    assert sum(name.startswith("_experiment/") for name in inputs) == 4
    manifest = {name: {"sha256": sha_bytes(content), "bytes": len(content)} for name, content in sorted(inputs.items())}
    write_json(HERE / "input-manifest.json", manifest)
    write_json(HERE / "composition.json", {"historicalArchiveSha256": sha_bytes(previous_archive_bytes),
               "historicalManifestSha256": sha_bytes(previous_manifest_bytes), "applicationConfigTestFiles": 189,
               "unchangedResearchHelpers": 4, "changedApplicationInputs": changes,
               "orchestrationRunnerSha256": sha_bytes(Path(__file__).read_bytes())})
    archive = HERE / "inputs.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, content in sorted(inputs.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(content), 0o644, 0
            tar.addfile(item, io.BytesIO(content))
    return manifest, archive


def download_outputs(root, record, suffix=""):
    """Always preserve failure outputs; never unpack a path supplied by application code."""
    script = r'''
import hashlib,io,json,pathlib,sys,tarfile
out=pathlib.Path(ROOT)/'out'; payload=io.BytesIO(); manifest={}
with tarfile.open(fileobj=payload,mode='w:gz') as tar:
 for path in sorted(out.rglob('*')) if out.exists() else []:
  if not path.is_file(): continue
  assert not path.is_symlink() and path.suffix in {'.json','.xml','.txt','.log'}
  name=path.relative_to(out).as_posix(); data=path.read_bytes()
  manifest[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  entry=tarfile.TarInfo(name); entry.size=len(data); entry.mode=0o644
  tar.addfile(entry,io.BytesIO(data))
 data=(json.dumps(manifest,indent=2)+'\n').encode();entry=tarfile.TarInfo('_remote-output-manifest.json')
 entry.size=len(data);entry.mode=0o644;tar.addfile(entry,io.BytesIO(data))
sys.stdout.buffer.write(payload.getvalue())
'''.replace("ROOT", repr(root))
    payload = remote_python(script)
    output_archive = HERE / ("outputs" + suffix + ".tar.gz")
    assert not output_archive.exists()
    output_archive.write_bytes(payload)
    output = HERE / ("results" + suffix)
    output.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        members = tar.getmembers()
        names = [member.name for member in members]
        assert len(names) == len(set(names))
        for entry in members:
            name = PurePosixPath(entry.name)
            assert entry.isfile() and not name.is_absolute() and ".." not in name.parts
            target = output.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(entry).read())
    expected = json.loads((output / "_remote-output-manifest.json").read_text())
    actual = {path.relative_to(output).as_posix(): {"sha256": sha_bytes(path.read_bytes()), "bytes": path.stat().st_size}
              for path in sorted(output.rglob("*")) if path.is_file() and path.name != "_remote-output-manifest.json"}
    assert actual == expected, "Downloaded output digests differ from the remote frozen output bytes"
    write_json(HERE / ("output-manifest" + suffix + ".json"), actual)
    record["downloadedOutputs"] = len(actual)
    record["outputArchiveSha256"] = sha_bytes(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true",
                        help="Resume the frozen, transferred original run; never refreeze source")
    parser.add_argument("--prepared", action="store_true",
                        help="Use the locally reviewed archive without composing or changing its bytes")
    args = parser.parse_args()
    assert not (args.resume and args.prepared)
    suffix = "-retry1" if args.resume else ""
    execution = HERE / ("execution" + suffix + ".json")
    assert not execution.exists(), "Do not replace an existing run; preserve its evidence"
    assert not (HERE / ("results" + suffix)).exists()
    assert not (HERE / ("output-manifest" + suffix + ".json")).exists()
    if args.resume:
        original_path = HERE / "execution.json"
        original_bytes = original_path.read_bytes()
        original = json.loads(original_bytes)
        assert original["state"] == "failed_not_cleaned"
        assert "dependencyPreparationExitCode" not in original, "Only resume the pre-install failure"
        assert original["host"] == "admin-vps" and original["image"] == IMAGE and original["runtime"] == "runc"
        archive = HERE / "inputs.tar.gz"
        manifest_bytes = (HERE / "input-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        assert sha_bytes(archive.read_bytes()) == original["inputArchiveSha256"]
        assert sha_bytes(manifest_bytes) == original["inputManifestSha256"]
        assert archive.stat().st_size == original["inputArchiveBytes"] and len(manifest) == original["inputFiles"]
        root = original["remoteTemp"]
        record = {key: original[key] for key in (
            "host", "image", "runtime", "remoteTemp", "inputFiles", "inputArchiveBytes",
            "inputArchiveSha256", "inputManifestSha256", "workspaceHead", "sourceIdentity",
            "realMoneyUsed", "realPaymentTransportUsed", "thirdPartyMcpCodeExecuted",
            "dependencyPreparationNetwork", "testsAndLedgerTraceNetwork", "selectedTests",
        )}
        record.update({"startedAt": utcnow(), "state": "resuming_original_frozen_inputs",
                       "originalExecution": "execution.json", "originalExecutionSha256": sha_bytes(original_bytes),
                       "orchestrationRunnerSha256": sha_bytes(Path(__file__).read_bytes()),
                       "frozenRunnerSha256": manifest["_experiment/run_linux.py"]["sha256"]})
    else:
        if args.prepared:
            review = json.loads((HERE / "payload-review.json").read_text())
            manifest_bytes = (HERE / "input-manifest.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            archive = HERE / "inputs.tar.gz"
            assert sha_bytes(manifest_bytes) == review["inputManifestSha256"]
            assert sha_bytes(archive.read_bytes()) == review["inputArchiveSha256"]
            assert len(manifest) == review["inputFiles"] == 193
            for name, meta in manifest.items():
                if name.startswith("_experiment/"):
                    continue
                current = (HUB / name).read_bytes()
                assert {"sha256": sha_bytes(current), "bytes": len(current)} == meta, name
        else:
            manifest, archive = freeze_inputs()
        root = remote(["mktemp", "-d", REMOTE_PREFIX + "XXXXXX"]).decode().strip()
        record = {
            "startedAt": utcnow(), "host": "admin-vps", "image": IMAGE, "runtime": "runc",
            "remoteTemp": root, "inputFiles": len(manifest),
            "inputArchiveBytes": archive.stat().st_size, "inputArchiveSha256": sha_bytes(archive.read_bytes()),
            "inputManifestSha256": sha_bytes((HERE / "input-manifest.json").read_bytes()),
            "workspaceHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
            "sourceIdentity": "exact current local source bytes; not a published aimarket-hub release",
            "realMoneyUsed": False, "realPaymentTransportUsed": False, "thirdPartyMcpCodeExecuted": False,
            "dependencyPreparationNetwork": "bridge, locked binary wheels only",
            "testsAndLedgerTraceNetwork": "none", "selectedTests": TESTS,
            "state": "frozen_not_transferred",
            "orchestrationRunnerSha256": sha_bytes(Path(__file__).read_bytes()),
            "compositionManifestSha256": sha_bytes((HERE / "composition.json").read_bytes()),
        }
    assert root.startswith(REMOTE_PREFIX) and "/" not in root[len(REMOTE_PREFIX):]
    write_json(execution, record)
    try:
        if not args.resume:
            subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(archive),
                            "admin-vps:" + root + "/inputs.tar.gz"], check=True)
        prepare = r'''
import hashlib,json,os,pathlib,tarfile
root=pathlib.Path(ROOT); work=root/'work';out=root/'out';deps=root/'deps'
manifest=MANIFEST
archive_sha=ARCHIVE_SHA
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==archive_sha
for directory in (out,deps):
 if directory.exists():
  assert directory.is_dir() and not directory.is_symlink() and not any(directory.iterdir()), ('Refuse nonempty existing state',str(directory))
 else:directory.mkdir()
reuse_work=work.exists()
if reuse_work:
 assert work.is_dir() and not work.is_symlink()
 existing={path.relative_to(work).as_posix():path for path in work.rglob('*') if path.is_file()}
 assert set(existing)==set(manifest), 'Existing source tree is not exactly the frozen input set'
 for name,path in existing.items():
  assert not path.is_symlink() and path.stat().st_size==manifest[name]['bytes']
  assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest[name]['sha256']
else:work.mkdir()
(work/'data').mkdir(exist_ok=True)
assert not (work/'data').is_symlink() and not any((work/'data').iterdir())
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(manifest)
 assert {m.name for m in members}==set(manifest)
 for member in members:
  assert member.isfile() and member.name in manifest
  path_name=pathlib.PurePosixPath(member.name)
  assert not path_name.is_absolute() and '..' not in path_name.parts
  data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==manifest[member.name]['sha256']
  assert len(data)==manifest[member.name]['bytes']
  if not reuse_work:
   path=work/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o644)
os.chmod(root,0o755)
for directory in (out,deps):os.chown(directory,65532,65532)
print(json.dumps({'verifiedFiles':len(manifest),'archiveSha256':archive_sha,'reusedVerifiedSourceTree':reuse_work}))
'''.replace("ROOT", repr(root)).replace("ARCHIVE_SHA", repr(record["inputArchiveSha256"])).replace("MANIFEST", repr(manifest))
        record["remoteInputVerification"] = json.loads(remote_python(prepare))
        record["state"] = "verified_remote_sources"
        write_json(execution, record)

        def container(network, deps_mode="ro"):
            command = [
                "docker", "run", "--rm", "--runtime", "runc", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", "768m", "--memory-swap", "768m",
                "--cpus", "1", "--pids-limit", "128", "--network", network,
                "--tmpfs", "/tmp:rw,nosuid,noexec,size=256m",
                "--tmpfs", "/work/data:rw,nosuid,noexec,size=64m,uid=65532,gid=65532", "--user", "65532:65532",
                "-v", root + "/work:/work:ro", "-v", root + "/out:/out:rw",
                "-v", root + "/deps:/deps:" + deps_mode, "--workdir", "/work",
                "-e", "PYTHONPATH=/deps:/work", "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-e", "PYTHONUNBUFFERED=1", "-e", "AIMARKET_AUTO_CRAWL=0",
                "-e", "AIMARKET_UPDATE_CHECK=0", "-e", "AIMARKET_DATA_DIR=/tmp/hub-data",
                "-e", "AIMARKET_CHANNELS_DB_PATH=/tmp/micky-channel-default.db",
                "--entrypoint", "python", IMAGE,
            ]
            return command

        prep = container("bridge", "rw") + ["/work/_experiment/prepare_dependencies.py"]
        record["dependencyPreparationCommand"] = prep
        write_json(execution, record)
        record["dependencyPreparationExitCode"] = run_logged(prep, "dependency-preparation" + suffix + ".log")
        write_json(execution, record)
        if record["dependencyPreparationExitCode"] != 0:
            raise RuntimeError("Dependency preparation failed; preserve its output and remote directory")

        metadata = container("none") + ["/work/_experiment/runtime_metadata.py"]
        record["runtimeMetadataCommand"] = metadata
        record["runtimeMetadataExitCode"] = run_logged(metadata, "runtime-metadata" + suffix + ".log")
        write_json(execution, record)
        if record["runtimeMetadataExitCode"] != 0:
            raise RuntimeError("Runtime metadata failed")

        tests = container("none") + ["-m", "pytest", "-o", "cache_dir=/tmp/micky-pytest-cache",
                                      "--tb=short", "-rA", "--junitxml=/out/junit.xml", *record["selectedTests"]]
        record["pytestCommand"] = tests
        write_json(execution, record)
        record["pytestExitCode"] = run_logged(tests, "linux-tests" + suffix + ".log")
        write_json(execution, record)
        trace = container("none") + ["/work/_experiment/trace_ledger.py", "--out", "/out/ledger-trace.json"]
        record["ledgerTraceCommand"] = trace
        record["ledgerTraceExitCode"] = run_logged(trace, "ledger-trace" + suffix + ".log")
        write_json(execution, record)
        if record["pytestExitCode"] != 0 or record["ledgerTraceExitCode"] != 0:
            raise RuntimeError("Tests or ledger trace failed; preserve all evidence for investigation")
        verification = r'''
import hashlib,json,pathlib,xml.etree.ElementTree as ET
root=pathlib.Path(ROOT);manifest=MANIFEST;work=root/"work";out=root/"out"
for name,meta in manifest.items():
 path=work/name;assert not path.is_symlink()
 assert {"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}==meta,name
suites=ET.parse(out/"junit.xml").getroot()
cases=list(suites.iter("testcase"))
assert len(cases)==146 and not list(suites.iter("failure")) and not list(suites.iter("error")) and not list(suites.iter("skipped"))
trace=json.loads((out/"ledger-trace.json").read_text())
assert len(trace["steps"])==14
payload={"verifiedInputs":len(manifest),"passedCases":len(cases),"failedCases":0,"skippedCases":0,
 "traceSteps":len(trace["steps"]),"traceChecks":len(trace["passed_checks"]),"currentSourceNotPublishedWheel":True}
(out/"verification.json").write_text(json.dumps(payload,indent=2)+"\n")
print(json.dumps(payload))
'''.replace("ROOT", repr(root)).replace("MANIFEST", repr(manifest))
        record["postRunVerification"] = json.loads(remote_python(verification))
        record["state"] = "passed_not_cleaned"
    except BaseException as exc:
        record["state"] = "failed_not_cleaned"
        record["failure"] = concise_error(exc)
        raise
    finally:
        record["finishedAt"] = utcnow()
        write_json(execution, record)
        try:
            download_outputs(root, record, suffix)
        except BaseException as exc:
            record["outputDownloadError"] = concise_error(exc)
            write_json(execution, record)
            raise
        write_json(execution, record)
        print(json.dumps({"state": record["state"], "remoteTemp": root,
                          "downloadedOutputs": record.get("downloadedOutputs", 0)}), flush=True)


if __name__ == "__main__":
    main()
