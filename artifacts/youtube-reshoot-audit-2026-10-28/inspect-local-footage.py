#!/usr/bin/env python3
"""Read-only source/hash and sampled-frame audit for the latest two video batches."""
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROMO = REPO.parent / 'PromoMaterials/blip'
SEASON = PROMO / 'youtube-season-something-pinged'
MODELS = REPO / 'pingblip/memeforge/public/models'
REPAIRED = {'spark-moth','rust-crown','winged-bolt','cola-cube','caramel-bust','graveyard-shift','taxi-larva'}

def sha(file):
 h=hashlib.sha256()
 with file.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def probe(file):
 return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height,r_frame_rate','-of','json',str(file)]))

v14=json.loads((SEASON/'v14-action-first/final/manifest.json').read_text())
v13=json.loads((SEASON/'v13-ten-redesigns/base/portrait-manifest.json').read_text())
rows=[]
for batch,manifest in [('v14-action-first',v14),('v13-ten-redesigns',v13)]:
 for ep in manifest:
  file=SEASON/ep['file'] if batch.startswith('v14') else SEASON/batch/'final'/ep['file']
  row={k:ep[k] for k in ('id','slug','name','kind','sources','sourceModelSHA256','capture','shots') if k in ep}
  row.update(batch=batch,file=str(file),sha256=sha(file),manifestHashMatches=sha(file)==ep['sha256'] if 'sha256' in ep else None,stream=probe(file))
  row['featuredRepairedModelIntersection']=sorted(REPAIRED&{row['slug']})
  if batch.startswith('v13'):
   model=MODELS/(row['slug']+'.glb')
   row['sourceModelMatchesCurrent']=sha(model)==ep.get('sourceModelSHA256')
  else:
   row['sourceModelChecks']=[]
   for source in ep.get('sources',[]):
    source_file=PROMO/source['file']
    source_check={'file':source['file'],'sourceExists':source_file.exists(),'manifestHash':source.get('sha256')}
    if source_file.exists():source_check['sourceHashMatchesManifest']=sha(source_file)==source.get('sha256')
    if source_file.suffix=='.glb':
     source_check['modelId']=source_file.stem
     source_check['repairedToday']=source_file.stem in REPAIRED
     source_check['sourceModelMatchesCurrent']=sha(MODELS/source_file.name)==source.get('sha256')
    row['sourceModelChecks'].append(source_check)
  rows.append(row)

def frame_sheet(row):
 duration=float(row['stream']['format']['duration'])
 times=[round(.15+(duration-.45)*i/5,3) for i in range(6)]
 stem=row['batch']+'-'+row['id']
 folder=HERE/'frames'/stem;folder.mkdir(parents=True,exist_ok=True)
 for i,t in enumerate(times):
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',row['file'],'-frames:v','1','-vf','scale=360:-2',str(folder/f'{i}.jpg')],check=True)
 # ffmpeg image2 input reads only the six files that this audit generated.
 sheet=HERE/(stem+'-contact.jpg')
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate','1','-i',str(folder/'%d.jpg'),'-vf','tile=3x2:padding=4:margin=4:color=0x151a21','-frames:v','1',str(sheet)],check=True)
 row['sampleTimesSeconds']=times;row['contactSheet']=str(sheet.relative_to(REPO))
 return row['id']

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for episode in pool.map(frame_sheet,rows):print('Inspected frames:',episode,flush=True)
report={'scope':'Read-only v14 nine final videos and v13 eight final portraits. Archived queue snapshots are not active rendered footage.','repairedModels':sorted(REPAIRED),'videos':rows}
(HERE/'local-footage-inventory.json').write_text(json.dumps(report,indent=2)+'\n')
print('Videos:',len(rows),'Featured repaired-model intersections:',sum(bool(row['featuredRepairedModelIntersection']) for row in rows))
print('v14 file hash mismatches:',[row['id'] for row in rows if row['manifestHashMatches'] is False])
print('v13 current-model mismatches:',[row['id'] for row in rows if row.get('sourceModelMatchesCurrent') is False])
