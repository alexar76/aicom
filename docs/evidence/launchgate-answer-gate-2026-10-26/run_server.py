"""Offline WARDEN build, host-boundary tests and historical structured projections."""
from datetime import datetime,timezone
from hashlib import sha256
import json,os,subprocess,sys
from pathlib import Path
IMAGE='sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
TESTS=['action','annotation-review','claude-plugin','flow-guard-answer-review','flow-guard-constraints','flow-guard-credential-boundary','flow-guard-gaps','flow-guard-gautam','flow-guard-gui-policy','flow-guard-home-paths','flow-guard-instructions','flow-guard-screen','flow-guard-secret-regression','flow-guard','mcp-client','pin-review-origin','result-screen','review-diff','toxic-flow','wrap-screen','wrap','answer-gate','answer-gate-host','packaging']
def now():return datetime.now(timezone.utc).isoformat()
def put(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 assert sys.platform=='linux';root=Path(sys.argv[1]);assert root.parent==Path('/tmp') and root.name.startswith('warden-answer-gate-')
 project=root/'study/project';out=root/'out';out.mkdir();os.chown(out,65532,65532)
 manifest=json.loads((root/'input-manifest.json').read_text())
 for name,m in manifest.items():assert sha256((root/'study'/name).read_bytes()).hexdigest()==m['sha256'],name
 for directory,_,files in os.walk(project):
  os.chown(directory,65532,65532)
  for name in files:os.chown(Path(directory)/name,65532,65532)
 record={'startedAt':now(),'host':'factory-vps','image':IMAGE,'runtime':'runc','testNetwork':'none','dependencyNetwork':'bridge','inputFiles':len(manifest),'newModelCalls':0,'githubWrites':False,'npmPublished':False,'completed':False,'checks':[]}
 def container(entry='node',network='none'):
  return ['docker','run','--rm','--runtime','runc','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--network',network,'--user','65532:65532','--memory','1536m','--cpus','2','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,noexec,size=256m','-v',str(project)+':/work:rw','-v',str(root/'study/research')+':/study:ro','-v',str(out)+':/out:rw','--workdir','/work','-e','HOME=/tmp/warden-home','-e','npm_config_cache=/tmp/npm-cache','-e','PYTHONDONTWRITEBYTECODE=1','--entrypoint',entry,IMAGE]
 def check(name,command):
  with (out/(name+'.log')).open('wb') as log:code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
  record['checks'].append({'name':name,'exitCode':code,'logSha256':sha256((out/(name+'.log')).read_bytes()).hexdigest()});put(out/'execution.json',record)
  print(json.dumps({'stage':name,'exitCode':code}),flush=True);assert code==0,name
 try:
  check('dependencies',container('npm','bridge')+['ci','--ignore-scripts','--no-audit','--no-fund'])
  check('build',container('npm')+['run','build'])
  check('typecheck',container('npm')+['run','typecheck'])
  check('answer-gate-tests',container()+['node_modules/vitest/vitest.mjs','run','test/answer-gate.test.ts','test/answer-gate-host.test.ts','--maxWorkers=1','--no-file-parallelism','--reporter=default','--reporter=json','--outputFile.json=/out/answer-gate-vitest.json'])
  check('warden-tests',container()+['node_modules/vitest/vitest.mjs','run',*['test/'+n+'.test.ts' for n in TESTS],'--maxWorkers=1','--no-file-parallelism','--reporter=default','--reporter=json','--outputFile.json=/out/vitest.json'])
  check('redteam',container()+['scripts/redteam/flow-redteam.mjs','/out/redteam.json','--check'])
  check('historical-replay',container()+['/study/replay.mjs'])
  record['completed']=True
 finally:
  check('collect-generated',container('sh')+['-c','mkdir -p /out/generated/claude-plugin && cp -R /work/dist /out/generated/ && cp -R /work/claude-plugin/scripts /out/generated/claude-plugin/'])
  record['finishedAt']=now();put(out/'execution.json',record)
if __name__=='__main__':
 try:main()
 except BaseException as error:print(json.dumps({'fatalType':type(error).__name__}),flush=True);sys.exit(1)
