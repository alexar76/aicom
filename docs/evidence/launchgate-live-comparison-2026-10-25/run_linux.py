#!/usr/bin/env python3
"""Freeze own sources, test, run the authorized USD 1 comparison, collect, then clean up."""
from datetime import datetime,timezone
import argparse,hashlib,io,json
from pathlib import Path,PurePosixPath
import re,subprocess,tarfile

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[2]
HOST='factory-vps'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST]
PREFIX='/tmp/launchgate-live-20261025.'
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def remote(script):return subprocess.check_output(SSH+['python3 -'],input=script.encode())
def freeze(state):
 frozen={}
 previous=json.loads((HERE.parent/'launchgate-warning-diagnostics-2026-10-25/input-manifest.json').read_text())
 for name in previous:
  if name.startswith('project/'):
   path=WORKSPACE/'warden'/name.removeprefix('project/')
   assert path.is_file() and not path.is_symlink()
   frozen[name]=path.read_bytes();frozen[name].decode('utf-8')
 for path in sorted(HERE.iterdir()):
  if path.is_file() and path.suffix in {'.py','.mjs','.json','.md'} and path.name!='README.md':
   frozen['research/'+path.name]=path.read_bytes()
 baseline=HERE.parent/'auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz'
 frozen['baseline.tgz']=baseline.read_bytes()
 assert sha(frozen['baseline.tgz'])=='5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
 manifest={n:{'sha256':sha(b),'bytes':len(b)} for n,b in frozen.items()}
 put(state/'input-manifest.json',manifest)
 archive=state/'inputs.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for name,b in sorted(frozen.items()):
   info=tarfile.TarInfo(name);info.size=len(b);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(b))
 return manifest,archive

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,default=HERE/'run-01');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
 state=args.state;state.mkdir(parents=True,exist_ok=True)
 assert not (state/'execution.json').exists(),'Preserve existing attempts; new state required'
 manifest,archive=freeze(state)
 record={'preparedAt':datetime.now(timezone.utc).isoformat(),'host':HOST,'inputFiles':len(manifest),
  'archiveBytes':archive.stat().st_size,'archiveSha256':sha(archive.read_bytes()),'budgetUSD':1,
  'maxAttempts':1100,'publicCommentsSent':False,'npmPublished':False}
 put(state/'preparation.json',record);print(json.dumps(record),flush=True)
 if args.prepare_only:return
 root=remote('import subprocess;print(subprocess.check_output(["mktemp","-d",'+repr(PREFIX+'XXXXXX')+'],text=True).strip())').decode().strip()
 assert re.fullmatch(re.escape(PREFIX)+r'[A-Za-z0-9]{6}',root)
 record['remoteTemp']=root;put(state/'execution.json',record)
 subprocess.run(['scp','-q','-o','BatchMode=yes',str(archive),HOST+':'+root+'/inputs.tar.gz'],check=True)
 script='''import pathlib,hashlib,tarfile,json
root=pathlib.Path(ROOT);manifest=MANIFEST
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==ARCHIVE_SHA
study=root/'study';study.mkdir();baseline=root/'baseline';baseline.mkdir()
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(manifest) and {m.name for m in members}==set(manifest)
 for m in members:
  parts=pathlib.PurePosixPath(m.name);assert m.isfile() and not parts.is_absolute() and '..' not in parts.parts
  b=tar.extractfile(m).read();assert hashlib.sha256(b).hexdigest()==manifest[m.name]['sha256']
  p=study/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
with tarfile.open(study/'baseline.tgz','r:gz') as tar:
 for m in tar.getmembers():
  p=pathlib.PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts and p.parts[0]=='package'
  if m.isdir():continue
  assert m.isfile();target=baseline/m.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(tar.extractfile(m).read())
(root/'input-manifest.json').write_text(json.dumps(manifest))
print(json.dumps({'verifiedFiles':len(manifest)}))
'''.replace('ROOT',repr(root)).replace('MANIFEST',repr(manifest)).replace('ARCHIVE_SHA',repr(record['archiveSha256']))
 record['verifiedInputs']=json.loads(remote(script));put(state/'execution.json',record)
 command=SSH+['python3 -B '+root+'/study/research/remote_run.py --root '+root]
 with (state/'supervisor.log').open('wb') as log:
  child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  for line in child.stdout:
   log.write(line);log.flush();print(line.decode(errors='replace').rstrip(),flush=True)
  record['remoteExitCode']=child.wait()
 put(state/'execution.json',record)
 collect='''import pathlib,hashlib,json,tarfile,io,sys
root=pathlib.Path(ROOT);out=root/'out';files={}
for p in out.rglob('*'):
 assert not p.is_symlink()
 if p.is_file():files['out/'+p.relative_to(out).as_posix()]=p
for directory in ['dist','claude-plugin/scripts']:
 for p in (root/'study/project'/directory).glob('*'):
  if p.is_file() and not p.is_symlink() and (directory=='dist' or p.name.startswith('flow-guard')):files['generated/'+p.relative_to(root/'study/project').as_posix()]=p
manifest={n:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for n,p in files.items()}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
 for n,p in sorted(files.items()):tar.add(p,arcname=n,recursive=False)
 b=(json.dumps(manifest,indent=2)+'\\n').encode();info=tarfile.TarInfo('output-manifest.json');info.size=len(b);tar.addfile(info,io.BytesIO(b))
sys.stdout.buffer.write(buffer.getvalue())
'''.replace('ROOT',repr(root))
 data=remote(collect);(state/'outputs.tar.gz').write_bytes(data)
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
  hashes=json.load(tar.extractfile('output-manifest.json'))
  for m in tar.getmembers():
   parsed=PurePosixPath(m.name);assert m.isfile() and not parsed.is_absolute() and '..' not in parsed.parts
   b=tar.extractfile(m).read()
   if m.name!='output-manifest.json':assert sha(b)==hashes[m.name]['sha256']
   p=state/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 record.update(outputSha256=sha(data),verifiedOutputs=len(hashes),collectedAt=datetime.now(timezone.utc).isoformat())
 put(state/'execution.json',record)
 # A failed run is also preserved before cleanup; only this exact owned root is removed.
 cleanup='''import pathlib,subprocess,shutil,json
root=pathlib.Path(ROOT);assert str(root).startswith(PREFIX) and root.is_dir() and not root.is_symlink()
active=subprocess.check_output(['docker','ps','--format','{{.Mounts}}'],text=True);assert str(root) not in active
shutil.rmtree(root);print(json.dumps({'removed':str(root),'absent':not root.exists()}))
'''.replace('ROOT',repr(root)).replace('PREFIX',repr(PREFIX))
 put(state/'cleanup.json',json.loads(remote(cleanup)))
 print(json.dumps({'stage':'collected-and-cleaned','exitCode':record['remoteExitCode'],'outputs':len(hashes)}),flush=True)
 if record['remoteExitCode']:raise SystemExit('Checks or model phase failed; evidence preserved')

if __name__=='__main__':main()
