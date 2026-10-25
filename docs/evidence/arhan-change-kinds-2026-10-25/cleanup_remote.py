#!/usr/bin/env python3
"""Verify downloaded result hashes, then remove only this study's private temp dir."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    record = json.loads((HERE / 'execution.json').read_text())
    assert record['state'] == 'downloaded_not_cleaned'
    root = record['remoteTemp']
    assert re.fullmatch(r'/tmp/arhan-change-kinds-20261025\.[A-Za-z0-9]+', root)
    expected = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                for name in ('summary.json', 'transitions.jsonl', 'servers.jsonl', 'manifest.json')}
    code = '''import hashlib,json,pathlib,re,shutil
from datetime import datetime,timezone
root=pathlib.Path(ROOT)
expected=EXPECTED
assert re.fullmatch(r'/tmp/arhan-change-kinds-20261025\\.[A-Za-z0-9]+',str(root))
assert not root.is_symlink() and (root/'source'/'analyze.py').is_file()
actual={name:hashlib.sha256((root/'out'/name).read_bytes()).hexdigest() for name in expected}
assert actual==expected, 'Downloaded output differs from remote output'
shutil.rmtree(root)
print(json.dumps({'removedDirectory':str(root),'removed':not root.exists(),'outputSha256':actual,
                  'cleanedAt':datetime.now(timezone.utc).isoformat()}))
'''.replace('ROOT', repr(root)).replace('EXPECTED', repr(expected))
    result = json.loads(subprocess.check_output(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps',
         shlex.join(['python3', '-c', code])], text=True))
    assert result['removed']
    (HERE / 'cleanup.json').write_text(json.dumps(result, indent=2) + '\n')
    record['state'] = 'cleaned'
    record['cleanedAt'] = result['cleanedAt']
    (HERE / 'execution.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
