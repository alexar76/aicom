#!/usr/bin/env python3
"""Verify completed synthetic-payment and saved-answer studies before removing their own temp roots."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']
record = json.loads((HERE / 'execution-retry3.json').read_text())
assert record['pytestExitCode'] == 0 and record['ledgerTraceExitCode'] == 0
suites = ET.parse(HERE / 'results-retry3/junit-retry3.xml').findall('.//testsuite')
assert sum(int(s.get('tests', 0)) for s in suites) == 146
assert not any(int(s.get(key, 0)) for s in suites for key in ('failures', 'errors', 'skipped'))


def clean(evidence, root, source_prefix, source, outputs, extra_source=None):
    assert not (evidence / 'cleanup.json').exists()
    for name, item in outputs.items():
        local = evidence / ('results-retry3' if evidence == HERE else '') / name
        assert hashlib.sha256(local.read_bytes()).hexdigest() == item['sha256']
    script = '''import pathlib,hashlib,json,shutil,datetime
root=pathlib.Path(ROOT)
assert root.is_dir() and not root.is_symlink()
assert str(root) in ('/tmp/micky-payment-20261025.m1NOxm','/tmp/launchgate-audit-20261025.pUNyUd')
sources=SOURCES;outputs=OUTPUTS;extra=EXTRA
def verify(base,expected):
 for name,meta in expected.items():
  p=base/name
  assert p.is_file() and not p.is_symlink(),name
  assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['sha256'],name
verify(root/PREFIX,sources);verify(root/'out',outputs)
assert {str(p.relative_to(root/'out')) for p in (root/'out').rglob('*') if p.is_file()}==set(outputs)
if extra:verify(root/'study',extra)
shutil.rmtree(root)
assert not root.exists()
print(json.dumps({'removed':True,'remoteTemp':str(root),'verifiedInputs':len(sources)+len(extra),
'verifiedOutputs':len(outputs),'recordedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
'''.replace('ROOT', repr(root)).replace('SOURCES', repr(source)).replace('OUTPUTS', repr(outputs))
    script = script.replace('EXTRA', repr(extra_source or {})).replace('PREFIX', repr(source_prefix))
    result = subprocess.check_output(SSH + ['python3 -'], input=script.encode())
    (evidence / 'cleanup.json').write_bytes(result)
    print(result.decode())


clean(HERE, record['remoteTemp'], 'work', json.loads((HERE / 'input-manifest.json').read_text()),
      json.loads((HERE / 'output-manifest-retry3.json').read_text()))
launch = HERE.parent / 'launchgate-methodology-2026-10-25'
first = json.loads((launch / 'execution.json').read_text())
retry = json.loads((launch / 'execution-probe-retry.json').read_text())
assert first['exitCodes'][:2] == [0, 0] and retry['exitCode'] == 0
outputs = {name: {'sha256': hashlib.sha256((launch / name).read_bytes()).hexdigest()}
           for name in ('saved-answer-audit.json', 'published-stop-observations.json')}
clean(launch, first['remoteTemp'], 'study', first['inputs'], outputs,
      {'probe_stop_retry.mjs': {'sha256': retry['sourceSha256']}})
