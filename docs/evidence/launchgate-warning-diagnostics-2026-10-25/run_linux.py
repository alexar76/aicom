#!/usr/bin/env python3
"""Freeze own WARDEN sources; isolated Linux build, regression tests and saved-answer replay.
No model calls, package publication, Git operations, secret/config mounts or production changes.
"""
from datetime import datetime, timezone
import hashlib, io, json
from pathlib import Path, PurePosixPath
import re, shlex, subprocess, tarfile

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[2]
WARDEN=WORKSPACE/'warden'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','admin-vps']
IMAGE='sha256:e1b65057659c168cb8510100daeca2f95d6e3f7ec081ed1b98f217591359b7a3'
PREFIX='/tmp/launchgate-warning-20261025.'
TESTS=sorted('test/'+p.name for p in (WARDEN/'test').glob('*.test.ts') if p.name.startswith('flow-guard') or p.name in {
 'wrap.test.ts','wrap-screen.test.ts','toxic-flow.test.ts','result-screen.test.ts','annotation-review.test.ts',
 'mcp-client.test.ts','review-diff.test.ts','pin-review-origin.test.ts','claude-plugin.test.ts','action.test.ts'})

def sha(data):return hashlib.sha256(data).hexdigest()
def put(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def remote(script):return subprocess.check_output(SSH+['python3 -'],input=script.encode())
def stamp():return datetime.now(timezone.utc).isoformat()

def freeze():
 frozen={}
 def add(path,name):
  assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(WORKSPACE)
  assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
  body=path.read_bytes()
  if path.suffix!='.tgz':body.decode('utf-8');assert b'\x00' not in body
  frozen[name]=body
 for directory,suffixes in [('src',{'.ts'}),('test',{'.ts','.mjs','.json'}),('claude-plugin',{'.mjs','.json','.md'}),('.claude-plugin',{'.json'}),('action',{'.sh'})]:
  for p in sorted((WARDEN/directory).rglob('*')):
   if p.is_file() and p.suffix in suffixes:add(p,'project/'+p.relative_to(WARDEN).as_posix())
 for name in ['package.json','package-lock.json','tsconfig.json','vitest.config.ts','action.yml','.pre-commit-hooks.yaml',
              'scripts/sync-flow-guard.mjs','scripts/redteam/flow-redteam.mjs','scripts/redteam/flow-gate.mjs',
              'scripts/selection-probe/audit_warnings.mjs','examples/atomic-screen-server.mjs']:
  add(WARDEN/name,'project/'+name)
 study=HERE.parent/'launchgate-tie-selection-2026-10-25'
 add(study/'linux-run/collection-06/out/main/runs.jsonl','research/runs.jsonl')
 add(study/'fixtures.json','research/fixtures.json')
 add(HERE.parent/'auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz','baseline.tgz')
 assert sha(frozen['baseline.tgz'])=='5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
 add(Path(__file__),'research/run_linux.py')
 manifest={n:{'sha256':sha(b),'bytes':len(b)} for n,b in frozen.items()}
 put(HERE/'input-manifest.json',manifest)
 archive=HERE/'inputs.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for n,b in sorted(frozen.items()):
   item=tarfile.TarInfo(n);item.size=len(b);item.mode=0o644;item.mtime=0
   tar.addfile(item,io.BytesIO(b))
 return manifest,archive

def main():
 assert not (HERE/'execution.json').exists(),'Preserve previous attempts; use a new evidence directory'
 manifest,archive=freeze()
 record={'startedAt':stamp(),'host':'admin-vps','image':IMAGE,'modelCalls':0,'selectedTests':TESTS,
         'inputFiles':len(manifest),'inputBytes':sum(v['bytes'] for v in manifest.values()),
         'archiveBytes':archive.stat().st_size,'archiveSha256':sha(archive.read_bytes())}
 put(HERE/'preparation.json',record)
 print(json.dumps(record),flush=True)
 if '--prepare-only' in __import__('sys').argv:return
 root=remote("import subprocess;print(subprocess.check_output(['mktemp','-d',"+repr(PREFIX+'XXXXXX')+"],text=True).strip())").decode().strip()
 assert re.fullmatch(re.escape(PREFIX)+r'[A-Za-z0-9]{6}',root)
 record['remoteTemp']=root;put(HERE/'execution.json',record)
 subprocess.run(['scp','-q','-o','BatchMode=yes',str(archive),'admin-vps:'+root+'/inputs.tar.gz'],check=True)
 script='''import pathlib,hashlib,tarfile,os,json,subprocess
root=pathlib.Path(ROOT);manifest=MANIFEST
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==ARCHIVE_SHA
assert json.loads(subprocess.check_output(['docker','image','inspect',IMAGE]))[0]['Id']==IMAGE
study=root/'study';study.mkdir();out=root/'out';out.mkdir();baseline=root/'baseline';baseline.mkdir()
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 members=tar.getmembers();assert len(members)==len(manifest) and {m.name for m in members}==set(manifest)
 for m in members:
  assert m.isfile() and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts
  data=tar.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==manifest[m.name]['sha256']
  p=study/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
with tarfile.open(study/'baseline.tgz','r:gz') as tar:
 for m in tar.getmembers():
  parts=pathlib.PurePosixPath(m.name);assert not parts.is_absolute() and '..' not in parts.parts and parts.parts[0]=='package'
  if m.isdir():continue
  assert m.isfile();p=baseline/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
os.chmod(root,0o755);os.chown(out,65532,65532)
for directory,_,files in os.walk(study/'project'):
 os.chown(directory,65532,65532)
 for n in files:os.chown(pathlib.Path(directory)/n,65532,65532)
print(json.dumps({'verifiedInputFiles':len(manifest)}))
'''.replace('ROOT',repr(root)).replace('MANIFEST',repr(manifest)).replace('ARCHIVE_SHA',repr(record['archiveSha256'])).replace('IMAGE',repr(IMAGE))
 record['verification']=json.loads(remote(script));put(HERE/'execution.json',record)
 def container(network='none',entry='node'):
  return ['docker','run','--rm','--runtime','runc','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
   '--memory','1536m','--memory-swap','1536m','--cpus','2','--pids-limit','128','--network',network,
   '--tmpfs','/tmp:rw,nosuid,noexec,size=384m','--user','65532:65532',
   '-v',root+'/study/project:/work:rw','-v',root+'/study/research:/research:ro','-v',root+'/baseline:/baseline:ro',
   '-v',root+'/out:/out:rw','--workdir','/work','-e','HOME=/tmp/warden-home','-e','WARDEN_STATE_DIR=/tmp/warden-state',
   '-e','npm_config_cache=/tmp/npm-cache','--entrypoint',entry,IMAGE]
 commands=[
 ('dependencies',container('bridge','npm')+['ci','--ignore-scripts','--no-audit','--no-fund']),
 ('build',container(entry='npm')+['run','build']),
 ('typecheck',container(entry='npm')+['run','typecheck']),
 ('tests',container()+['node_modules/vitest/vitest.mjs','run',*TESTS,'--maxWorkers=1','--no-file-parallelism','--reporter=default','--reporter=json','--outputFile.json=/out/vitest.json']),
 ('redteam',container()+['scripts/redteam/flow-redteam.mjs','/out/redteam.json','--check']),
 ('baseline-replay',container()+['scripts/selection-probe/audit_warnings.mjs','/baseline/package','/research/runs.jsonl','/research/fixtures.json','/out/baseline-replay.json']),
 ('candidate-replay',container()+['scripts/selection-probe/audit_warnings.mjs','/work','/research/runs.jsonl','/research/fixtures.json','/out/candidate-replay.json']),
 ]
 record['commands']=[]
 for name,command in commands:
  print('START '+name,flush=True)
  entry={'name':name,'command':command,'startedAt':stamp()};record['commands'].append(entry);put(HERE/'execution.json',record)
  with (HERE/(name+'.log')).open('wb') as log:
   result=subprocess.run(SSH+[shlex.join(command)],stdout=log,stderr=subprocess.STDOUT)
  entry.update(exitCode=result.returncode,finishedAt=stamp());put(HERE/'execution.json',record)
  print(name+' exit '+str(result.returncode)+'\n'+(HERE/(name+'.log')).read_text(errors='replace')[-2200:],flush=True)
  if result.returncode and name in {'dependencies','build'}:break
 # Collect output and compiled artifacts. The source manifest remains frozen.
 collect='''import pathlib,hashlib,json,tarfile,io,sys
root=pathlib.Path(ROOT);study=root/'study';manifest=MANIFEST
source_changes=[]
for name,info in manifest.items():
 p=study/name
 if hashlib.sha256(p.read_bytes()).hexdigest()!=info['sha256'] and not name.startswith('project/claude-plugin/scripts/flow-guard'):source_changes.append(name)
assert not source_changes,source_changes
files={}
for p in (root/'out').rglob('*'):
 if p.is_file() and not p.is_symlink():files['results/'+p.relative_to(root/'out').as_posix()]=p
for directory in ['dist','claude-plugin/scripts']:
 for p in (study/'project'/directory).glob('*'):
  if p.is_file() and not p.is_symlink() and (directory=='dist' or p.name.startswith('flow-guard')):files['generated/'+p.relative_to(study/'project').as_posix()]=p
hashes={n:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for n,p in files.items()}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
 for name,path in sorted(files.items()):tar.add(path,arcname=name,recursive=False)
 b=(json.dumps(hashes,indent=2)+'\\n').encode();item=tarfile.TarInfo('output-manifest.json');item.size=len(b);tar.addfile(item,io.BytesIO(b))
sys.stdout.buffer.write(buffer.getvalue())
'''.replace('ROOT',repr(root)).replace('MANIFEST',repr(manifest))
 data=remote(collect);(HERE/'outputs.tar.gz').write_bytes(data)
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
  hashes=json.load(tar.extractfile('output-manifest.json'))
  for m in tar.getmembers():
   path=PurePosixPath(m.name);assert m.isfile() and not path.is_absolute() and '..' not in path.parts
   b=tar.extractfile(m).read()
   if m.name!='output-manifest.json':assert sha(b)==hashes[m.name]['sha256']
   p=HERE/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 record.update(finishedAt=stamp(),outputArchiveSha256=sha(data),verifiedOutputs=len(hashes),passed=len(record['commands'])==len(commands) and all(c['exitCode']==0 for c in record['commands']))
 put(HERE/'execution.json',record);print(json.dumps({'passed':record['passed'],'verifiedOutputs':len(hashes)}),flush=True)
 # Cleanup only our exact temporary root after a verified local collection.
 cleanup='''import pathlib,shutil,json,subprocess
root=pathlib.Path(ROOT)
assert str(root).startswith(PREFIX) and root.is_dir() and not root.is_symlink()
active=subprocess.check_output(['docker','ps','--format','{{.Mounts}}'],text=True)
assert str(root) not in active
shutil.rmtree(root)
print(json.dumps({'removed':str(root),'absent':not root.exists()}))
'''.replace('ROOT',repr(root)).replace('PREFIX',repr(PREFIX))
 put(HERE/'cleanup.json',json.loads(remote(cleanup)))
 if not record['passed']:raise SystemExit('Preserved failing test evidence; repair sources and use a fresh run directory')

if __name__=='__main__':main()
