#!/usr/bin/env python3
"""Verify input/output hashes, then remove only this experiment's remote temporary directory."""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
execution = json.loads((HERE / 'execution.json').read_text())
root = execution['remoteTemp']
assert root == '/tmp/kevin-fake-billing-20261025.o3bMc3'
assert execution['experimentExitCode'] == 0 and execution['backendSelfTestExitCode'] == 0
result = json.loads((HERE / 'results/result.json').read_text())
assert result['failedRuns'] == 0 and result['passedRuns'] == 78
inputs = json.loads((HERE / 'input-manifest.json').read_text())
outputs = json.loads((HERE / 'output-manifest.json').read_text())
script = '''import pathlib,hashlib,json,shutil,datetime
root=pathlib.Path(ROOT)
assert root.is_dir() and not root.is_symlink() and str(root)=='/tmp/kevin-fake-billing-20261025.o3bMc3'
inputs=INPUTS;outputs=OUTPUTS
def verify(folder,expected):
 for name,meta in expected.items():
  path=folder/name
  assert path.is_file() and not path.is_symlink(),name
  assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256'],name
verify(root/'study',inputs);verify(root/'out',outputs)
assert {str(p.relative_to(root/'out')) for p in (root/'out').rglob('*') if p.is_file()}==set(outputs)
shutil.rmtree(root)
assert not root.exists()
print(json.dumps({'removed':True,'remoteTemp':str(root),'verifiedInputFiles':len(inputs),'verifiedOutputFiles':len(outputs),
'recordedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
'''.replace('ROOT', repr(root)).replace('INPUTS', repr(inputs)).replace('OUTPUTS', repr(outputs))
response = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps',
                                    shlex.join(['python3', '-c', script])], text=True)
(HERE / 'cleanup.json').write_text(response + '\n')
print(response)
