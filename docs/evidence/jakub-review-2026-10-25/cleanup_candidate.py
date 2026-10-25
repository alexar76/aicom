#!/usr/bin/env python3
"""Verify downloaded results and frozen source, then remove only this study's temporary directory."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = '/tmp/jakub-candidate-20261025.xB0Wdi'
assert json.loads((HERE / 'candidate-final-execution.json').read_text())['testExitCode'] == 0
assert json.loads((HERE / 'candidate/result.json').read_text())['assertions'] == {'passed': 19, 'failed': 0}
sources = json.loads((HERE / 'candidate-final-source-manifest.json').read_text())
built = json.loads((HERE / 'candidate-final-built-manifest.json').read_text())
results = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE / 'candidate').iterdir()
           if p.suffix in ('.json', '.txt') and p.name not in ('checksums.json', 'execution.json')}
script = '''import hashlib,json,pathlib,shutil,datetime
root=pathlib.Path(ROOT)
assert str(root)=='/tmp/jakub-candidate-20261025.xB0Wdi' and root.is_dir() and not root.is_symlink()
sources=SOURCES;built=BUILT;results=RESULTS
def verify(base,expected,metadata):
 for name,value in expected.items():
  path=base/name
  assert path.is_file() and not path.is_symlink()
  assert hashlib.sha256(path.read_bytes()).hexdigest()==(value['sha256'] if metadata else value),name
verify(root/'project',sources,True);verify(root/'project',built,True)
actual={p.name for p in (root/'results').iterdir()}
assert actual==set(results),(actual,set(results))
verify(root/'results',results,False)
shutil.rmtree(root)
assert not root.exists()
print(json.dumps({'remoteTemp':str(root),'removed':True,'verifiedSourceFiles':len(sources),'verifiedBuiltFiles':len(built),
'verifiedResultFiles':len(results),'recordedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
'''.replace('ROOT', repr(ROOT)).replace('SOURCES', repr(sources)).replace('BUILT', repr(built)).replace('RESULTS', repr(results))
result = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps',
                                  shlex.join(['python3', '-c', script])], text=True)
(HERE / 'candidate/cleanup.json').write_text(result + '\n')
print(result)
