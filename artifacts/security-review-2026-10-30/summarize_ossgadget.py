"""Stream a large SARIF into bounded, reviewable evidence; preserve raw in temporary cache."""
import collections,hashlib,json
from pathlib import Path
import ijson
OUT=Path(__file__).resolve().parent
src=OUT/'ossgadget.sarif';counts=collections.Counter();files=collections.Counter();examples=[];total=0
with src.open('rb') as f:
 for r in ijson.items(f,'runs.item.results.item'):
  total+=1;rid=r.get('ruleId') or r.get('rule',{}).get('id') or '?';msg=r.get('message',{}).get('text','');counts[str(rid)+' '+str(msg)[:100]]+=1
  for l in r.get('locations',[]):
   loc=l.get('physicalLocation',{});name=loc.get('artifactLocation',{}).get('uri','');files[name]+=1
  if len(examples)<30:examples.append(r)
h=hashlib.sha256()
with src.open('rb') as f:
 while b:=f.read(1024*1024):h.update(b)
summary={'scanner':'OSSGadget 0.2.38','runtime':'dotnet10 roll-forward from net8','rules':'10 official BackdoorRules files at v0.2.38','source_inventory':'source-inventory.json','results':total,'rules':dict(counts),'files_with_findings':len(files),'top_files':files.most_common(30),'examples':examples,'raw_bytes':src.stat().st_size,'raw_sha256':h.hexdigest(),'raw_cache':'/private/tmp/aicom-security-review-20261030/ossgadget.sarif'}
(OUT/'ossgadget-summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n');src.replace(summary['raw_cache']);print(total,'results',len(files),'files',counts.most_common(12))
