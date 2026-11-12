"""Run the frozen exact-row read-only proof using existing normal service DB auth.

No credential discovery, environment output, Hub import, migration or database mutation.
Native environment is loaded only to reproduce the already-known unit's normal context.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
HELPER=HERE/'read_paid_ledger.py'
EXPECTED='138a1eb6d8203d7926b05689252b39ba2c106735ec8243d337db6baa638ca8ab'
raw=HELPER.read_bytes()
assert hashlib.sha256(raw).hexdigest()==EXPECTED
CODE=raw.decode()
SELECTORS=json.loads((HERE/'paid-ledger-selectors.json').read_text())

REMOTE=r'''
import json,os,pathlib,pwd,subprocess,sys
name=NAME
code=CODE
selected=SELECTED
if name=='attested':
 p=subprocess.run(['docker','exec','-i','attested-memory-hub-hub-1','python','-c',code],input=json.dumps(selected),capture_output=True,text=True,timeout=45)
else:
 pid=subprocess.check_output(['systemctl','show','independentai-hub.service','-p','MainPID','--value'],text=True).strip()
 assert pid.isdigit() and int(pid)>0
 proc=pathlib.Path('/proc')/pid
 runtime={}
 for item in (proc/'environ').read_bytes().split(b'\0'):
  if b'=' in item:
   k,v=item.split(b'=',1);runtime[k.decode()]=v.decode()
 user=pwd.getpwuid(proc.stat().st_uid).pw_name
 p=subprocess.run(['runuser','-u',user,'--','/opt/independentai/venvs/hub-3.16.0-rpc-security-20261031/bin/python','-c',code],input=json.dumps(selected),capture_output=True,text=True,env=runtime,cwd=os.readlink(proc/'cwd'),timeout=45)
try:result=json.loads(p.stdout)
except (ValueError,TypeError):result={'ok':False,'error_type':'RemoteHelperOutputUnavailable','raw_rows_emitted':False}
print(json.dumps(result))
'''

def run(name):
    remote=REMOTE.replace('name=NAME','name='+repr(name)).replace('code=CODE','code='+repr(CODE)).replace('selected=SELECTED','selected='+repr(SELECTORS[name]))
    host='attested' if name=='attested' else 'indep'
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no',host,'python3 -'],input=remote,capture_output=True,text=True,timeout=65)
        if p.returncode:raise RuntimeError('remote helper unavailable')
        d=json.loads(p.stdout)
    except Exception as exc:
        d={'ok':False,'error_type':type(exc).__name__,'error':'Scoped read-only proof unavailable; no raw diagnostic emitted','raw_rows_emitted':False}
    d.update(hub=name,helper_sha256=EXPECTED,standard_runtime_database_auth_used=True,credentials_or_environment_emitted=False)
    (HERE/(name+'-paid-ledger-proof.json')).write_text(json.dumps(d,indent=2)+'\n')
    return d

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,['independent','attested']))
    print(json.dumps(results,indent=2))
    raise SystemExit(0 if all(r.get('ok') for r in results) else 1)
