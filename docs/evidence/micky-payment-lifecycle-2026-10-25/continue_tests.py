#!/usr/bin/env python3
"""Retry only the runtime phase with an explicit writable synthetic channel database."""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('micky_runner', HERE / 'run_linux.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
parser = argparse.ArgumentParser()
parser.add_argument('--attempt3', action='store_true')
args = parser.parse_args()
phase = 'retry3' if args.attempt3 else 'retry2'
previous_name = 'execution-retry2.json' if args.attempt3 else 'execution-retry1.json'
prior = json.loads((HERE / previous_name).read_text())
prepared = json.loads((HERE / 'execution-retry1.json').read_text())
assert prepared['dependencyPreparationExitCode'] == 0 and prepared['runtimeMetadataExitCode'] == 0
root = prior['remoteTemp']
assert root == '/tmp/micky-payment-20261025.m1NOxm'
state_path = HERE / f'execution-{phase}.json'
assert not state_path.exists() and not (HERE / f'results-{phase}').exists()
record = {'startedAt': datetime.now(timezone.utc).isoformat(), 'remoteTemp': root,
          'sourceManifestSha256': prepared['inputManifestSha256'], 'resumes': previous_name,
          'reason': ('Give service default databases an empty writable /work/data tmpfs, leaving all frozen source read-only.' if args.attempt3 else
                     'The module-global ChannelLedger defaults to data/channels.db. Point it to writable /tmp in the read-only-source test container.'),
          'productionCodeChanged': False, 'state': 'prepared'}


def fixed(command):
    command = list(command)
    index = command.index('--entrypoint')
    if args.attempt3:
        command[index:index] = ['--tmpfs', '/work/data:rw,nosuid,noexec,size=64m,uid=65532,gid=65532']
    else:
        command[index:index] = ['-e', 'AIMARKET_CHANNELS_DB_PATH=/tmp/micky-channel-default.db']
    return [part.replace('/out/junit.xml', f'/out/junit-{phase}.xml').replace('/out/junit-retry2.xml', f'/out/junit-{phase}.xml')
                 .replace('/out/ledger-trace.json', f'/out/ledger-trace-{phase}.json')
            for part in command]


try:
    if args.attempt3:
        setup = "from pathlib import Path\np=Path('/tmp/micky-payment-20261025.m1NOxm/work/data')\nassert not p.is_symlink()\np.mkdir(exist_ok=True)\nassert not any(p.iterdir())\n"
        runner.remote_python(setup)
    record['pytestCommand'] = fixed(prior['pytestCommand'])
    if args.attempt3:
        record['pytestCommand'].insert(record['pytestCommand'].index('-rA'), '--tb=short')
    runner.write_json(state_path, record)
    record['pytestExitCode'] = runner.run_logged(record['pytestCommand'], f'linux-tests-{phase}.log')
    if args.attempt3:
        assert prior['ledgerTraceExitCode'] == 0
        record['ledgerTraceExitCode'] = 0
        record['ledgerTraceEvidence'] = 'results-retry2/ledger-trace-retry2.json; unchanged source; not rerun'
    else:
        record['ledgerTraceCommand'] = fixed(prior['ledgerTraceCommand'])
        record['ledgerTraceExitCode'] = runner.run_logged(record['ledgerTraceCommand'], f'ledger-trace-{phase}.log')
    record['state'] = 'passed_not_cleaned' if not (record['pytestExitCode'] or record['ledgerTraceExitCode']) else 'failed_not_cleaned'
finally:
    record['finishedAt'] = datetime.now(timezone.utc).isoformat()
    runner.download_outputs(root, record, '-' + phase)
    runner.write_json(state_path, record)
    print(json.dumps({key: record.get(key) for key in ('state', 'pytestExitCode', 'ledgerTraceExitCode', 'downloadedOutputs')}))
assert record['state'] == 'passed_not_cleaned', 'Preserve failed test evidence'
