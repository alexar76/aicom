"""Synthetic own-server boundary checks; no model calls. Keep remote data unless local collection is verified."""
from hashlib import sha256
import io,json,re,shlex,subprocess,tarfile
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2] if len(HERE.parents)>2 else HERE
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=4','factory-vps']
def remote(code):return subprocess.check_output(SSH+['python3 -'],input=code.encode())
def put(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def collect(root,state,receipt):
 code='''import pathlib,tarfile,io,json,hashlib
root=pathlib.Path(ROOT);files={}
for p in (root/'out').rglob('*'):
 if p.is_file() and not p.is_symlink():files['out/'+str(p.relative_to(root/'out'))]=p.read_bytes()
archive=root/'collected-outputs.tgz'
with tarfile.open(archive,mode='w:gz') as tar:
 for n,data in files.items():
  m=tarfile.TarInfo(n);m.size=len(data);tar.addfile(m,io.BytesIO(data))
 data=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in files.items()}).encode();m=tarfile.TarInfo('output-manifest.json');m.size=len(data);tar.addfile(m,io.BytesIO(data))
archive.chmod(0o600)
print(json.dumps({'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}))
'''.replace('ROOT',repr(root))
 expected=json.loads(remote(code))
 target=state/'outputs.tar.gz'
 subprocess.run(['scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=20','factory-vps:'+root+'/collected-outputs.tgz',str(target)],check=True)
 assert sha256(target.read_bytes()).hexdigest()==expected['sha256'] and target.stat().st_size==expected['bytes']
 with tarfile.open(target) as tar:
  hashes=json.load(tar.extractfile('output-manifest.json'))
  assert {m.name for m in tar.getmembers()}==set(hashes)|{'output-manifest.json'}
  for m in tar.getmembers():
   path=PurePosixPath(m.name);assert m.isfile() and not path.is_absolute() and '..' not in path.parts
   b=tar.extractfile(m).read()
   if m.name!='output-manifest.json':assert sha256(b).hexdigest()==hashes[m.name]
   p=state/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 receipt.update(outputArchiveSha256=expected['sha256'],verifiedOutputs=len(hashes),collectionVerified=True)
 put(state/'execution-local.json',receipt)
 receipt['cleanup']=json.loads(remote('import pathlib,shutil,json;p=pathlib.Path('+repr(root)+');shutil.rmtree(p);print(json.dumps({"absent":not p.exists()}))'))
 put(state/'execution-local.json',receipt)

SETUP="import pathlib,tarfile,hashlib,json\nroot=pathlib.Path(ROOT);manifest=MANIFEST\nstudy=root/'study';study.mkdir();root.chmod(0o755)\nwith tarfile.open(root/'inputs.tgz') as tar:\n assert {m.name for m in tar.getmembers()}==set(manifest)\n for m in tar.getmembers():\n  assert m.isfile();b=tar.extractfile(m).read();assert hashlib.sha256(b).hexdigest()==manifest[m.name]['sha256']\n  p=study/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)\n(root/'input-manifest.json').write_text(json.dumps(manifest))\n"
def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--run',default='run-01');parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--recover',action='store_true');args=parser.parse_args()
 assert re.fullmatch('run-[0-9]{2}',args.run)
 state=HERE/args.run;state.mkdir(exist_ok=True)
 if args.recover:
  receipt=json.loads((state/'execution-local.json').read_text());root=receipt['remoteRoot'];assert re.fullmatch('/tmp/warden-qingfeng-reference-[A-Za-z0-9_]+',root)
  assert not receipt.get('cleanup',{}).get('absent');collect(root,state,receipt);return
 assert not (state/'execution-local.json').exists()
 files={}
 for p in sorted((ROOT/'warden/src').glob('*.ts')):
  files['project/src/'+p.name]=p.read_bytes()
 for name in ['package.json','package-lock.json','tsconfig.json','vitest.config.ts','test/setup.ts','test/global-setup.ts','test/flow-guard-reference-egress.test.ts','test/flow-guard-credential-boundary.test.ts','test/flow-guard-secret-regression.test.ts','test/flow-guard-answer-review.test.ts','scripts/sync-flow-guard.mjs']:
  files['project/'+name]=(ROOT/'warden'/name).read_bytes()
 for p in sorted((ROOT/'warden/claude-plugin/scripts').glob('*.mjs')):
  files['project/claude-plugin/scripts/'+p.name]=p.read_bytes()
 for name in ['protocol.md','run_server.py']:
  files['research/'+name]=(HERE/name).read_bytes()
 files['run_server.py']=(HERE/'run_server.py').read_bytes()
 manifest={n:{'sha256':sha256(b).hexdigest(),'bytes':len(b)} for n,b in files.items()};put(state/'input-manifest.json',manifest)
 archive=state/'inputs.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for n,b in files.items():
   m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o644;tar.addfile(m,io.BytesIO(b))
 print(json.dumps({'preparedFiles':len(files),'archiveBytes':archive.stat().st_size,'newModelCalls':0}),flush=True)
 if args.prepare_only:return
 root=remote('import tempfile;print(tempfile.mkdtemp(prefix="warden-qingfeng-reference-",dir="/tmp"))').decode().strip();assert re.fullmatch('/tmp/warden-qingfeng-reference-[A-Za-z0-9_]+',root)
 receipt={'host':'factory-vps','remoteRoot':root,'files':len(files),'inputArchiveSha256':sha256(archive.read_bytes()).hexdigest(),'archiveBytes':archive.stat().st_size,'newModelCalls':0,'collectionVerified':False}
 put(state/'execution-local.json',receipt)
 try:
  subprocess.run(['scp','-q','-o','BatchMode=yes',str(archive),'factory-vps:'+root+'/inputs.tgz'],check=True)
  setup=SETUP.replace('ROOT',repr(root)).replace('MANIFEST',repr(manifest));remote(setup)
  command=['python3','-B',root+'/study/run_server.py',root]
  with (state/'supervisor.log').open('w') as log:
   process=subprocess.Popen(SSH+[shlex.join(command)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
   for line in process.stdout:log.write(line);log.flush();print(line,end='',flush=True)
   receipt['exitCode']=process.wait()
  put(state/'execution-local.json',receipt);collect(root,state,receipt)
 except BaseException as error:
  receipt['localFailureType']=type(error).__name__;put(state/'execution-local.json',receipt)
  print('Operation failed; remote evidence is retained unless verified collection and cleanup are recorded.',flush=True);raise
 assert receipt['exitCode']==0,receipt
 print('Collected verified offline outputs and removed owned temporary root.',flush=True)

if __name__=='__main__':main()
