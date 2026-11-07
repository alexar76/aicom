"""Preserve original formatting for semantically unchanged uv package blocks."""
import json,re,subprocess,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
results=[]
def semantic(text):
 d=tomllib.loads('[[package]]'+text)['package'][0]
 d.pop('sdist',None);d.pop('wheels',None)
 def rec(v):
  if isinstance(v,dict):return {k:rec(x) for k,x in v.items() if k!='upload-time'}
  if isinstance(v,list):return sorted((rec(x) for x in v),key=lambda x:json.dumps(x,sort_keys=True))
  return v
 return rec(d)
for row in json.loads((OUT/'lock-refresh.json').read_text()):
 path=Path(row['project'])/'uv.lock'
 old=subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT,text=True);new=(ROOT/path).read_text()
 oldchunks=old.split('[[package]]');newchunks=new.split('[[package]]');index={}
 for chunk in oldchunks[1:]:
  d=tomllib.loads('[[package]]'+chunk)['package'][0];index[(d['name'],d['version'])]=chunk
 n=0
 for i,chunk in enumerate(newchunks[1:],1):
  d=tomllib.loads('[[package]]'+chunk)['package'][0];key=(d['name'],d['version']);orig=index.get(key)
  if orig and semantic(orig)==semantic(chunk):newchunks[i]=orig;n+=1
 result='[[package]]'.join(newchunks)
 assert tomllib.loads(result)==tomllib.loads(new) or all(semantic(x)==semantic(y) for x,y in zip(result.split('[[package]]')[1:],new.split('[[package]]')[1:])),path
 (ROOT/path).write_text(result);results.append({'path':str(path),'original_blocks_preserved':n})
(OUT/'lock-format-preservation.json').write_text(json.dumps(results,indent=2)+'\n')
