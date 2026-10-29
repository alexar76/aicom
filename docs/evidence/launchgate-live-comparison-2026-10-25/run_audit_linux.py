#!/usr/bin/env python3
"""Run the independent artifact ledger audit in a new networkless Linux container."""
import hashlib,io,json
from pathlib import Path,PurePosixPath
import re,shlex,subprocess,tarfile
HERE=Path(__file__).resolve().parent
STATE=HERE/'run-02'
HOST='factory-vps';SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST]
IMAGE='sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
def sha(b):return hashlib.sha256(b).hexdigest()
def remote(script):return subprocess.check_output(SSH+['python3 -'],input=script.encode())
def main():
 assert not (STATE/'independent-audit.json').exists()
 data={'outputs.tar.gz':(STATE/'outputs.tar.gz').read_bytes(),'audit.py':(HERE/'audit_outputs.py').read_bytes(),'fixtures.json':(HERE/'fixtures.json').read_bytes()}
 archive=STATE/'audit-inputs.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for n,b in data.items():
   m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o644;tar.addfile(m,io.BytesIO(b))
 manifest={n:sha(b) for n,b in data.items()}
 root=remote('import tempfile;print(tempfile.mkdtemp(prefix="launchgate-data-audit-",dir="/tmp"))').decode().strip()
 assert re.fullmatch(r'/tmp/launchgate-data-audit-[A-Za-z0-9_]+',root)
 subprocess.run(['scp','-q','-o','BatchMode=yes',str(archive),HOST+':'+root+'/inputs.tgz'],check=True)
 prep='''import pathlib,tarfile,hashlib,json,os
root=pathlib.Path(ROOT);manifest=MANIFEST;data=root/'data';data.mkdir();out=root/'result';out.mkdir()
with tarfile.open(root/'inputs.tgz','r:gz') as tar:
 for m in tar.getmembers():
  assert m.isfile() and m.name in manifest;b=tar.extractfile(m).read();assert hashlib.sha256(b).hexdigest()==manifest[m.name]
  (root/m.name).write_bytes(b)
with tarfile.open(root/'outputs.tar.gz','r:gz') as tar:
 expected=json.load(tar.extractfile('output-manifest.json'))
 for m in tar.getmembers():
  p=pathlib.PurePosixPath(m.name)
  if not m.name.startswith('out/'):continue
  assert m.isfile() and not p.is_absolute() and '..' not in p.parts
  b=tar.extractfile(m).read();assert hashlib.sha256(b).hexdigest()==expected[m.name]['sha256']
  target=data/m.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b);target.chmod(0o644)
os.chmod(root,0o755);os.chown(out,65532,65532)
'''.replace('ROOT',repr(root)).replace('MANIFEST',repr(manifest))
 remote(prep)
 command=['docker','run','--rm','--runtime','runc','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
  '--memory','512m','--cpus','1','--pids-limit','64','--user','65532:65532','--tmpfs','/tmp:rw,nosuid,noexec,size=64m',
  '-v',root+':/study:ro','-v',root+'/result:/result:rw','--entrypoint','python3',IMAGE,
  '-B','/study/audit.py','--out','/study/data/out','--fixtures','/study/fixtures.json','--write','/result/audit.json']
 result=subprocess.run(SSH+[shlex.join(command)],capture_output=True)
 (STATE/'independent-audit.log').write_bytes(result.stdout+result.stderr)
 record={'host':HOST,'image':IMAGE,'runtime':'runc','network':'none','exitCode':result.returncode,
         'inputs':manifest,'archiveSha256':sha(archive.read_bytes()),'command':command,'remoteTemp':root}
 if result.returncode==0:
  b=remote('from pathlib import Path;import sys;sys.stdout.buffer.write(Path('+repr(root+'/result/audit.json')+').read_bytes())')
  (STATE/'independent-audit.json').write_bytes(b);record['resultSha256']=sha(b)
  print(b.decode())
 else:print((result.stdout+result.stderr).decode(errors='replace')[-3000:])
 cleanup=remote('import shutil,pathlib,json;p=pathlib.Path('+repr(root)+');shutil.rmtree(p);print(json.dumps({"removed":str(p),"absent":not p.exists()}))')
 record['cleanup']=json.loads(cleanup)
 (STATE/'independent-audit-execution.json').write_text(json.dumps(record,indent=2)+'\n')
 assert result.returncode==0,'Audit failed; log retained'
if __name__=='__main__':main()
