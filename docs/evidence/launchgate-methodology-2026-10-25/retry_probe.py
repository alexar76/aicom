#!/usr/bin/env python3
"""Repeat only the observation probe with support for the published bundled module layout."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
execution = json.loads((HERE / 'execution.json').read_text())
assert execution['exitCodes'] == [0, 0, 1]
root = execution['remoteTemp']
assert root == '/tmp/launchgate-audit-20261025.pUNyUd'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']
source = HERE / 'probe_stop.mjs'
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
state = HERE / 'execution-probe-retry.json'
assert not state.exists()
subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(source), 'admin-vps:' + root + '/study/probe_stop_retry.mjs'], check=True)
verify = f"import pathlib,hashlib\nassert hashlib.sha256(pathlib.Path({(root + '/study/probe_stop_retry.mjs')!r}).read_bytes()).hexdigest()=={source_sha!r}\n"
subprocess.run(SSH + ['python3 -'], input=verify.encode(), check=True)
command = [part.replace('/study/probe_stop.mjs', '/study/probe_stop_retry.mjs') for part in execution['commands'][2]]
result = subprocess.run(SSH + [shlex.join(command)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(HERE / 'linux-probe-retry.log').write_bytes(result.stdout)
state.write_text(json.dumps({'remoteTemp': root, 'sourceSha256': source_sha, 'command': command,
                            'exitCode': result.returncode, 'reason': 'Published artifact bundles answer hook into flow-guard.js; optional split-module hash may be absent.'}, indent=2) + '\n')
assert result.returncode == 0, result.stdout.decode(errors='replace')[-2000:]
data = subprocess.check_output(SSH + [shlex.join(['cat', root + '/out/published-stop-observations.json'])])
report = json.loads(data)
assert all(row['expectationMet'] for row in report['observations'])
(HERE / 'published-stop-observations.json').write_bytes(data)
print(json.dumps({'observations': len(report['observations']), 'passed': True, 'moduleLayout': report['moduleLayout']}))
