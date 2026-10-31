from pathlib import Path
import sys,json,datetime as dt,time,hashlib,shutil
from zoneinfo import ZoneInfo
import yaml
P=Path('/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/blip/youtube-season-something-pinged');R=P/'v15-mini-stories';sys.path.insert(0,str(P));import upload_youtube as u
sys.path.insert(0,str(P/'v14-action-first/source'));from publish_batch import fetch,status_fields
sys.path.insert(0,str(P/'v5-week-one/source'));from manage_queue import schedule_video
S=R/'publication-state.json'
def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
y=u.get_youtube(open_browser=False);u.assert_pingblip(u.whoami(y),for_upload=True)
manifest=json.loads((R/'final/manifest.json').read_text());meta=yaml.safe_load(u.META_PATH.read_text());log=u.load_log()
if S.exists():state=json.loads(S.read_text())
else:
 before=json.loads((P/'v14-action-first/qa/youtube-latest.json').read_text());save(R/'qa/youtube-before.json',before)
 old=fetch(y,[log['shorts'][i]['videoId'] for i in ['PB42','PB43','CL20']]);assert all(v['status']['privacyStatus']=='private' and v['status'].get('publishAt') for v in old.values())
 state={'order':['PB44','PB42','PB45','PB43','PB46','CL20'],'items':{}}
 for n,eid in enumerate(state['order']):
  when=dt.datetime(2026,10,31,16 if n%2==0 else 22,tzinfo=ZoneInfo('Europe/Moscow'))+dt.timedelta(days=n//2)
  state['items'][eid]={'publishAt':when.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),'moscow':when.isoformat(),'videoId':log['shorts'].get(eid,{}).get('videoId')}
 save(S,state)
for ep in manifest:
 item=state['items'][ep['id']]
 if item.get('videoId'):continue
 assert not item.get('uploadStarted'),'Unknown upload outcome; inspect channel first'
 assert hashlib.sha256((P/ep['file']).read_bytes()).hexdigest()==ep['sha256']
 item['uploadStarted']=u.now();save(S,state)
 desc='A short story edited from previously recorded real PingBlip gameplay. Waiting shortened. Comic captions describe the pet; game pips are in-game credits, not money.\nPlay free: https://pingblip.com/\nMusic: PingBlip original, AI-generated.\n#PingBlip #BrowserGame #CreatureCollector'
 vid=u.upload_video(y,P/ep['file'],ep['title']+' #Shorts',desc,['PingBlip','BrowserGame','CreatureCollector'],meta['channel'],'private',contains_synthetic_media=True)
 item['videoId']=vid;save(S,state)
 log=u.load_log();log['shorts'][ep['id']]={'videoId':vid,'url':'https://youtube.com/shorts/'+vid,'title':ep['title'],'file':ep['file'],'privacy':'private','uploadedAt':u.now()};u.save_log(log)
 meta['episodes'][ep['id']]={'title':ep['title'],'description':desc,'video':ep['file'],'short_video':ep['file'],'contains_synthetic_media':True}
 if ep['id'] not in meta['upload_order']:meta['upload_order'].append(ep['id'])
 u.META_PATH.write_text(yaml.safe_dump(meta,allow_unicode=True,sort_keys=False));print('UPLOADED',ep['id'],vid,flush=True)
for attempt in range(12):
 actual=fetch(y,[i['videoId'] for i in state['items'].values()])
 if all(v.get('processingDetails',{}).get('processingStatus')=='succeeded' for v in actual.values()):break
 time.sleep(5)
else:raise RuntimeError('Processing pending; rerun saved IDs')
planpath=P/'v5-week-one/publication-plan.json';plan=json.loads(planpath.read_text());shutil.copy2(planpath,R/'qa/plan-before.json') if not (R/'qa/plan-before.json').exists() else None
for eid in state['order']:
 item=state['items'][eid];v=actual[item['videoId']];assert v['status']['privacyStatus']=='private'
 status=status_fields(v);status.update(privacyStatus='private',publishAt=item['publishAt'],containsSyntheticMedia=True);schedule_video(y,item['videoId'],status)

 for retry in range(10):
  check=fetch(y,[item['videoId']])[item['videoId']]
  if check['status'].get('publishAt')==item['publishAt']:break
  time.sleep(2)
 assert check['status'].get('publishAt')==item['publishAt'];item['verified']=True;save(S,state)
 row=next((r for r in plan if r['id']==eid),None)
 if row is None:
  ep=next(e for e in manifest if e['id']==eid);row={k:ep[k] for k in ['id','title','file','sha256']};row.update(series='story',format='gameplay');plan.append(row)
 row.update(publishAt=item['publishAt'],moscow=item['moscow'],newYork=dt.datetime.fromisoformat(item['moscow']).astimezone(ZoneInfo('America/New_York')).isoformat());save(planpath,plan)
 log=u.load_log();log['shorts'][eid].update(publishAt=row['publishAt'],scheduledMoscow=row['moscow'],scheduledLocal=row['newYork'],scheduleTimezone='Europe/Moscow');u.save_log(log)
 print('SCHEDULED',eid,row['moscow'],flush=True)
save(R/'publication-plan.json',[r for r in plan if r['id'] in state['order']]);after=fetch(y,[v['id'] for v in json.loads((R/'qa/youtube-before.json').read_text())['videos']]+[i['videoId'] for i in state['items'].values()])
changed={i['videoId'] for i in state['items'].values()}
for old in json.loads((R/'qa/youtube-before.json').read_text())['videos']:
 v=after[old['id']]
 assert v['snippet']==old['snippet']
 if old['id'] not in changed:assert v['status']==old['status']
save(R/'qa/youtube-verification.json',{'checkedAt':u.now(),'items':state['items'],'priorUnrelatedVideosUnchanged':True});print('VERIFIED')
