"""Bounded regressions: only temporary files, fake Docker/chown/watchdog; no containers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
HOSTS = ROOT / 'warden/scripts/scanner-comparison/hosts'
TOOLS = ['mcp-audit', 'truecopy', 'mcpsentry', 'mcp-shield']
RESULTS = []
FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, types
from pathlib import Path
root = Path(os.environ['FIXTURE_ROOT'])
def record(value):
    with (root / 'docker.jsonl').open('a') as handle:
        handle.write(json.dumps(value) + '\n')
args = sys.argv[1:]
record({'docker_args': args})
if args[0] == 'ps':
    sys.exit(0)
assert args[0] == 'run'
command = args[args.index('warden-cmp:20261016') + 1:]
if command[:2] == ['sh', '-c']:
    # Original scripts: run only this test's known payload in its private directory.
    sys.exit(subprocess.run(command, cwd=root, check=False).returncode)
assert command[:2] == ['python3', '-'], command
source = sys.stdin.read()
sys.argv = ['-', command[2]]
def fake_run(argv, **kwargs):
    record({'scanner_args': argv, 'kwargs': kwargs})
    return types.SimpleNamespace(returncode=int(os.environ.get('SCANNER_STATUS', '0')))
subprocess.run = fake_run
exec(compile(source, '<fixed-container-dispatcher>', 'exec'))
'''


def make_case(scratch, script, *, before=False, name='mcptox-decorated.v2_1', plan=None,
              cpus='2', cap='1.5', shares='128', workers=None, scanner_status=0, queued=False):
    work = scratch / 'work'
    for folder in ('retry', 'sets', 'raw'):
        (work / folder).mkdir(parents=True)
    (work / 'chain.log').write_text('pending\n' if queued else 'ALL-DONE attested\n')
    if queued:
        cap, shares, workers = '8', '512', 'AUDIT_W=6\nTC_W=8\nMS_W=8\nSH_W=32\n'
    if cap is not None:
        (work / 'cpus.cap').write_text(cap + '\n')
    if shares is not None:
        (work / 'cpu.shares').write_text(shares + '\n')
    if workers is not None:
        (work / 'workers.conf').write_text(workers)
    plan = {tool: ['server-1'] for tool in TOOLS} if plan is None else plan
    # Malicious SET is rejected before any file access; files use the valid fixture name.
    file_name = name if '/' not in name and '\0' not in name else 'unused'
    (work / 'retry' / f'{file_name}.json').write_text(json.dumps(plan))
    (work / 'sets' / f'{file_name}-config.json').write_text(json.dumps({
        'mcpServers': {'server-1': {'command': 'node', 'args': ['replay.mjs', 'fixture.json']}}
    }))
    for tool, keys in plan.items():
        if '/' in tool or '\0' in tool:
            continue
        folder = work / 'raw' / file_name / tool
        folder.mkdir(parents=True)
        (folder / 'server-1.json').write_text('original raw evidence\n')
    binary = scratch / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    for executable in ('chown', 'setsid'):
        target = binary / executable
        target.write_text('#!/bin/sh\nexit 0\n')
        target.chmod(0o755)
    if queued:
        # Advance readiness deterministically on the first wait, updating operator controls.
        # Only the clock is replaced; the helper still reads the real temporary files.
        (binary / 'sitecustomize.py').write_text('''import os, time
from pathlib import Path
if os.environ.get('ADVANCE_READINESS') == '1':
    original_sleep = time.sleep
    def advance_readiness(seconds):
        if seconds == 60:
            work = Path(os.environ['FIXTURE_ROOT']) / 'work'
            (work / 'cpus.cap').write_text('1.5\\n')
            (work / 'cpu.shares').write_text('128\\n')
            (work / 'workers.conf').write_text('AUDIT_W=2\\nTC_W=4\\nMS_W=3\\nSH_W=12\\n')
            (work / 'chain.log').write_text('ALL-DONE attested\\n')
        else:
            original_sleep(seconds)
    time.sleep = advance_readiness
''')
    original = OUT / script.replace('.sh', '.before.sh') if before else HOSTS / script
    code = original.read_text()
    # The only source substitution relocates the fixed production workspace into this fixture.
    code = code.replace('/opt/warden-cmp/20261016', str(work))
    copy = scratch / script
    copy.write_text(code)
    env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
           'FIXTURE_ROOT': str(scratch), 'SCANNER_STATUS': str(scanner_status)}
    if queued:
        env['PYTHONPATH'] = str(binary)
        env['ADVANCE_READINESS'] = '1'
    result = subprocess.run(['sh', str(copy), name, cpus], cwd=scratch, env=env,
                            capture_output=True, text=True, timeout=10)
    calls = [json.loads(line) for line in (scratch / 'docker.jsonl').read_text().splitlines()] if (scratch / 'docker.jsonl').exists() else []
    return work, result, calls


def check(label, assertion):
    with tempfile.TemporaryDirectory(prefix='warden-retry-regression-') as folder:
        assertion(Path(folder))
    RESULTS.append({'case': label, 'passed': True})


def rejected(scratch, script, **overrides):
    work, result, calls = make_case(scratch, script, **overrides)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert not calls, calls
    assert not (scratch / 'PWNED').exists()
    assert not (work / 'raw-firstpass').exists()
    assert not any((work / 'raw').glob('*-retry'))


def old_exploit(scratch, script):
    _, _, _ = make_case(scratch, script, before=True, name='corpus',
                        plan={'mcp-audit;touch${IFS}PWNED;#': ['server-1']})
    assert (scratch / 'PWNED').is_file(), 'original helper did not reproduce shell execution'


def normal(scratch, script, status=0, queued=False):
    workers = 'AUDIT_W=2\nTC_W=4\nMS_W=3\nSH_W=12\n'
    work, result, calls = make_case(scratch, script, workers=workers, scanner_status=status, queued=queued)
    assert result.returncode == status, (result.returncode, result.stderr)
    runs = [c['docker_args'] for c in calls if c.get('docker_args', [''])[0] == 'run']
    assert len(runs) == 1
    run = runs[0]
    assert '-i' in run and run[run.index('--cpus') + 1] == '1.5'
    assert run[run.index('--cpu-shares') + 1] == '128'
    assert run[run.index('--network') + 1] == 'none'
    assert '--runtime=runsc' in run and '--read-only' in run
    assert run[run.index('warden-cmp:20261016') + 1:][:2] == ['python3', '-']
    scanner = [c['scanner_args'] for c in calls if 'scanner_args' in c]
    assert [c[c.index('--only') + 1] for c in scanner] == TOOLS
    expected = ['2', '4', '3', '12'] if script == 'retry_cross.sh' else ['4'] * 4
    assert [c[c.index('--workers') + 1] for c in scanner] == expected
    assert all(c[:2] == ['python3', '/work/harness/run_competitors.py'] for c in scanner)
    if script == 'retry_set.sh':
        for tool in TOOLS:
            assert (work / 'raw-firstpass/mcptox-decorated.v2_1' / tool / 'server-1.json').read_text() == 'original raw evidence\n'
            assert not (work / 'raw/mcptox-decorated.v2_1' / tool / 'server-1.json').exists()
    else:
        for tool in TOOLS:
            config = json.loads((work / 'raw/mcptox-decorated.v2_1-retry' / f'{tool}-config.json').read_text())
            assert list(config['mcpServers']) == ['server-1']
            assert (work / 'raw/mcptox-decorated.v2_1' / tool / 'server-1.json').is_file()
    assert not (scratch / 'PWNED').exists()


for script in ('retry_set.sh', 'retry_cross.sh'):
    check(script + ': original JSON key executes marker', lambda p, s=script: old_exploit(p, s))
    attacks = [
        ('JSON scanner key shell syntax', {'plan': {'mcp-audit;touch${IFS}PWNED;#': ['server-1']}}),
        ('unknown scanner key', {'plan': {'unknown-scanner': ['server-1']}}),
        ('SET shell syntax', {'name': 'corpus;touch${IFS}PWNED;#'}),
        ('SET command substitution', {'name': 'corpus$(touch PWNED)'}),
        ('SET traversal', {'name': '../corpus'}),
        ('server traversal', {'plan': {'mcp-audit': ['../outside']}}),
        ('bad server-list schema', {'plan': {'mcp-audit': 'server-1'}}),
        ('CPUS option injection', {'cpus': '2 --privileged'}),
        ('CPU cap shell syntax', {'cap': '1;touch PWNED'}),
        ('CPU shares option injection', {'shares': '128 --privileged'}),
    ]
    for label, overrides in attacks:
        check(script + ': rejects ' + label, lambda p, s=script, o=overrides: rejected(p, s, **o))
    check(script + ': fixed dispatcher and preserved evidence', lambda p, s=script: normal(p, s))
    check(script + ': propagates scanner failure', lambda p, s=script: normal(p, s, 7))
check('retry_cross.sh: rejects executable workers.conf',
      lambda p: rejected(p, 'retry_cross.sh', workers='AUDIT_W=2\ntouch PWNED\n'))
check('retry_cross.sh: rejects invalid worker count',
      lambda p: rejected(p, 'retry_cross.sh', workers='AUDIT_W=0\n'))
check('retry_cross.sh: reads current caps and workers after readiness wait',
      lambda p: normal(p, 'retry_cross.sh', queued=True))
summary = {'cases': len(RESULTS), 'passed': len(RESULTS), 'results': RESULTS,
           'effects': 'temporary fixture files only; fake Docker/chown/watchdog; no real containers or hosts'}
(OUT / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
