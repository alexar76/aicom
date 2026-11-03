"""Upload six reviewed Shorts and mix them into the native UTC schedule.

No game server access. Never retry an upload with an unknown outcome.
Only status fields are changed on existing scheduled videos.
"""
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse, datetime as dt, hashlib, json, shutil, sys, time
import yaml
from snapshot import A, P, snapshot, u

R=P/'v18-return-and-explore'
STATE=A/'qa/publication-state.json'
PLAN=P/'v5-week-one/publication-plan.json'
QUEUE=P/'v5-week-one/queue-state.json'
UTC=dt.timezone.utc
NEW_ORDER=['PB58','PB59','PB60','PB61','PB62','PB63']
def old_order(state):return [eid for eid in state['order'] if not state['items'][eid]['new']]

def load(path):return json.loads(path.read_text())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');tmp.replace(path)
def parse(value):return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
def baseline():
    before=load(A/'qa/youtube-before.json')
    extra=A/'qa/youtube-before-supplement.json'
    if extra.exists():
        videos={v['id']:v for v in before['videos']}
        for v in load(extra)['videos']:videos.setdefault(v['id'],v)
        before={**before,'videos':list(videos.values())}
    return before
def fetch(y,ids):
    result={}
    for start in range(0,len(ids),50):
        videos=y.videos().list(part='snippet,status,processingDetails',id=','.join(ids[start:start+50])).execute().get('items',[])
        assert all(v['snippet']['channelId']==u.EXPECTED_CHANNEL_ID for v in videos)
        result.update({v['id']:v for v in videos})
    assert set(result)==set(ids),'Missing videos in readback'
    return result

def prepare():
    assert not STATE.exists(),'Resume saved publication state'
    eps=load(R/'final/manifest.json');qa=load(A/'qa/validation.json')
    assert {e['id'] for e in eps}==set(NEW_ORDER)
    assert {e['id'] for e in qa}==set(NEW_ORDER)
    for ep in eps:
        check=next(x for x in qa if x['id']==ep['id'])
        assert check['visualApproved'] and check['decodePassed'] and ep['visualApproved']
        assert check['sha256']==ep['sha256']==hashlib.sha256((P/ep['file']).read_bytes()).hexdigest()
    before=baseline();log=u.load_log()
    active=sorted([v for v in before['videos'] if v['status']['privacyStatus']=='private' and v['status'].get('publishAt')],key=lambda v:v['status']['publishAt'])
    logged={row['videoId']:eid for eid,row in log['shorts'].items()}
    old=[logged[v['id']] for v in active]
    assert len(old)>=10 and len(set(old))==len(old)
    assert all(v['status']['privacyStatus']=='private' for v in active)
    assert dt.datetime.now(UTC)-parse(before['checkedAt'])<dt.timedelta(hours=2)
    start=parse(active[0]['status']['publishAt'])
    assert start>dt.datetime.now(UTC)+dt.timedelta(minutes=30)
    assert (start.hour,start.minute)==(13,0)
    # Keep the existing order and place new continuation scenes after the
    # corresponding first feed or catch has appeared on the channel.
    anchors={'PB53':'PB58','PB56':'PB59','PB57':'PB60','PB43':'PB61','PB50':'PB62','PB46':'PB63'}
    assert set(anchors).issubset(old),'Review story dependencies against the current queue'
    order=[]
    for eid in old:
        order.append(eid)
        if eid in anchors:order.append(anchors[eid])
    assert {eid for eid in order if eid in NEW_ORDER}==set(NEW_ORDER)
    state={'createdAt':u.now(),'channelId':u.EXPECTED_CHANNEL_ID,
           'cadence':{'timezone':'UTC','dailyTimes':['13:00','19:00'],'fixedUtcAcrossDst':True,'audienceTimezone':'America/New_York'},
           'order':order,'items':{}}
    plan=load(PLAN);meta=yaml.safe_load(u.META_PATH.read_text())
    assert not any(eid in log['shorts'] for eid in NEW_ORDER)
    assert not any(r['id'] in NEW_ORDER for r in plan)
    existing_titles={v['snippet']['title'] for v in before['videos']}
    for rel in ['upload_log.json','upload_metadata.yaml','v5-week-one/publication-plan.json','v5-week-one/queue-state.json']:
        target=A/'qa/before'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/rel,target)
    for n,eid in enumerate(order):
        when=start+dt.timedelta(days=n//2,hours=6*(n%2))
        stamp=when.isoformat().replace('+00:00','Z')
        row=next((r for r in plan if r['id']==eid),None)
        if eid in NEW_ORDER:
            ep=next(e for e in eps if e['id']==eid)
            title,desc,tags=u.short_meta(ep,None)
            assert title not in existing_titles
            u.check_public_text(eid,title,desc)
            row={k:ep[k] for k in ['id','title','file','sha256']}
            row.update(series='clips' if ep['kind']=='library' else 'story',format=ep['kind'])
            plan.append(row)
            meta['episodes'][eid]={'title':ep['title'],'description':ep['description'],'video':ep['file'],'short_video':ep['file'],
                                   'tags':['PingBlip','BrowserGame','CreatureCollector',ep['name']], 'contains_synthetic_media':True}
            if eid not in meta['upload_order']:meta['upload_order'].append(eid)
        assert row
        previous=row.get('publishAt')
        row.update(publishAt=stamp,scheduleTimezone='UTC',newYork=when.astimezone(ZoneInfo('America/New_York')).isoformat(),moscow=when.astimezone(ZoneInfo('Europe/Moscow')).isoformat())
        state['items'][eid]={'new':eid in NEW_ORDER,'phase':'ready' if eid in NEW_ORDER else 'existing','row':row,
                             'previousPublishAt':previous,'videoId':log['shorts'].get(eid,{}).get('videoId')}
    future=[r['publishAt'] for r in plan if parse(r['publishAt'])>dt.datetime.now(UTC)]
    assert len(future)==len(order) and len(set(future))==len(order)
    capture=load(A/'qa/capture/capture-summary.json')
    assert capture['completed'] and capture['freshSession'] and capture['noAdminAccess']
    assert all(e['freshGameplay'] and e['sources'][0]['file']==str(R/'capture/raw-vertical.mp4') for e in eps)
    # Persist intent before external mutations. The heartbeat remains paused.
    save(STATE,state);save(PLAN,plan)
    u.META_PATH.write_text(yaml.safe_dump(meta,allow_unicode=True,sort_keys=False))
    save(R/'publication-plan.json',[state['items'][e]['row'] for e in order])
    for eid in order:print(eid,state['items'][eid]['row']['publishAt'],state['items'][eid]['row']['title'])

def upload(y,state):
    if state.get('nextUploadAttemptAt') and any(not state['items'][eid].get('videoId') for eid in NEW_ORDER):
        assert dt.datetime.now(UTC)>=parse(state['nextUploadAttemptAt']), 'Wait until '+state['nextUploadAttemptAt']
    meta=yaml.safe_load(u.META_PATH.read_text())
    actual=snapshot(y)
    before=baseline()
    old_by={v['id']:v for v in before['videos']}
    current_by={v['id']:v for v in actual['videos']}
    known_new={i['videoId'] for i in state['items'].values() if i['new'] and i.get('videoId')}
    assert set(current_by)==set(old_by)|known_new,'Channel changed; inspect before continuing'
    for eid in old_order(state):
        item=state['items'][eid];v=current_by[item['videoId']]
        if v['status']['privacyStatus']=='public' and parse(item['row']['publishAt'])<=dt.datetime.now(UTC):
            item.update(phase='published',publicationObservedAt=u.now());save(STATE,state)
            continue
        assert v['status']['privacyStatus']=='private'
        assert v['status'].get('publishAt') in [item['previousPublishAt'],item['row']['publishAt']]
    for eid in NEW_ORDER:
        item=state['items'][eid]
        if item.get('videoId'):continue
        assert item['phase'] not in ['upload_started','unknown_upload_outcome'],'Unknown upload outcome; inspect channel before retry'
        ep=meta['episodes'][eid];row=item['row'];file=P/row['file']
        assert hashlib.sha256(file.read_bytes()).hexdigest()==row['sha256']
        title,desc,tags=u.short_meta(ep,None)
        u.check_public_text(eid,title,desc)
        item.update(phase='upload_started',uploadStartedAt=u.now());save(STATE,state)
        try:
            vid=u.upload_video(y,file,title,desc,tags,meta['channel'],'private',contains_synthetic_media=True)
        except Exception as exc:
            item['phase']='upload_limit' if u.is_quota_error(exc) else 'unknown_upload_outcome'
            if item['phase']=='upload_limit':
                state['uploadLimitObservedAt']=u.now()
                state['nextUploadAttemptAt']=(dt.datetime.now(UTC)+dt.timedelta(hours=24,minutes=10)).isoformat()
            save(STATE,state)
            raise
        item.update(videoId=vid,phase='uploaded_private',url='https://youtube.com/shorts/'+vid,uploadedAt=u.now());save(STATE,state)
        log=u.load_log();log['shorts'][eid]={'videoId':vid,'url':item['url'],'title':title,'file':row['file'],'privacy':'private','uploadedAt':item['uploadedAt'],'captions':False,'thumbnail':False,'playlist':False};u.save_log(log)
        print('UPLOADED',eid,vid,flush=True)

def schedule(y,state):
    sys.path.insert(0,str(P/'v5-week-one/source'))
    from manage_queue import schedule_video
    meta=yaml.safe_load(u.META_PATH.read_text())
    ids=[item['videoId'] for item in state['items'].values() if item.get('videoId')]
    for attempt in range(24):
        actual=fetch(y,ids)
        failed=[v['id'] for v in actual.values() if v['status'].get('uploadStatus') in ['failed','rejected']]
        assert not failed,failed
        pending=[v['id'] for v in actual.values() if v.get('processingDetails',{}).get('processingStatus')!='succeeded']
        if not pending:break
        print('PROCESSING',len(pending),flush=True);time.sleep(5)
    else:raise RuntimeError('Processing pending; rerun saved IDs')
    # Move the tail first so earlier target slots are free before scheduling new items.
    mutation_order=list(reversed(old_order(state)))+NEW_ORDER
    fields=['privacyStatus','license','embeddable','publicStatsViewable','selfDeclaredMadeForKids','containsSyntheticMedia']
    for eid in mutation_order:
        item=state['items'][eid];when=item['row']['publishAt']
        if not item.get('videoId'):continue
        v=fetch(y,[item['videoId']])[item['videoId']]
        if v['status']['privacyStatus']=='public' and parse(when)<=dt.datetime.now(UTC):
            item.update(phase='published',publicationObservedAt=u.now());save(STATE,state)
            continue
        assert parse(when)>dt.datetime.now(UTC)+dt.timedelta(minutes=10)
        assert v['status']['privacyStatus']=='private'
        disclosure=bool(meta['episodes'][eid].get('contains_synthetic_media'))
        # YouTube documents this declaration on insert/update; it can be
        # omitted by list responses. Explicitly preserve the intended value
        # when changing the status part, rather than infer false from omission.
        if v['status'].get('publishAt')!=when or (disclosure and not item.get('syntheticDisclosureSentAt')):
            status={k:value for k,value in v['status'].items() if k in fields}
            status.update(privacyStatus='private',publishAt=when)
            if disclosure:status['containsSyntheticMedia']=True
            schedule_video(y,item['videoId'],status)
            if disclosure:item['syntheticDisclosureSentAt']=u.now();save(STATE,state)
        for attempt in range(8):
            check=fetch(y,[item['videoId']])[item['videoId']]
            if check['status'].get('publishAt')==when:break
            time.sleep(2)
        assert check['status'].get('publishAt')==when
        item.update(phase='scheduled',scheduleVerifiedAt=u.now());save(STATE,state)
        log=u.load_log();log['shorts'][eid].update(publishAt=when,scheduleTimezone='UTC',scheduledLocal=item['row']['newYork'],scheduledMoscow=item['row']['moscow']);u.save_log(log)
        print('SCHEDULED',eid,when,flush=True)

def verify(y,state):
    after=snapshot(y);save(A/'qa/youtube-after.json',after)
    actual={v['id']:v for v in after['videos']};before=baseline()
    before_by={v['id']:v for v in before['videos']}
    moved={state['items'][eid]['videoId'] for eid in old_order(state)}
    for old in before_by.values():
        v=actual[old['id']]
        for field in ['title','description','tags']:
            assert v['snippet'].get(field)==old['snippet'].get(field),(old['id'],field)
        if old['id'] not in moved:
            assert v['status']==old['status'],old['id']
        else:
            a={k:value for k,value in old['status'].items() if k!='publishAt'}
            b={k:value for k,value in v['status'].items() if k!='publishAt'}
            if v['status']['privacyStatus']=='public':
                item=next(i for i in state['items'].values() if i['videoId']==v['id'])
                assert parse(item['row']['publishAt'])<=dt.datetime.now(UTC)
            else:assert a==b,old['id']
    newids={i['videoId'] for i in state['items'].values() if i['new']}
    assert len(newids)==6 and newids.isdisjoint(before_by)
    assert set(before_by).issubset(actual)
    checks=[];meta=yaml.safe_load(u.META_PATH.read_text())
    for eid in state['order']:
        item=state['items'][eid];v=actual[item['videoId']];row=item['row']
        assert item['phase'] in ['scheduled','published']
        if parse(row['publishAt'])<=dt.datetime.now(UTC):assert v['status']['privacyStatus']=='public'
        else:assert v['status']['privacyStatus']=='private' and v['status']['publishAt']==row['publishAt']
        assert v['processingDetails']['processingStatus']=='succeeded'
        if item['new']:
            title,desc,_=u.short_meta(meta['episodes'][eid],None)
            assert v['snippet']['title']==title
            assert v['snippet']['description']==u.with_profile_cta(desc)
            assert item.get('syntheticDisclosureSentAt')
            assert v['status'].get('containsSyntheticMedia') is not False
        checks.append({'id':eid,'new':item['new'],'videoId':v['id'],'title':v['snippet']['title'],'url':'https://youtube.com/shorts/'+v['id'],'publishAt':row['publishAt'],'newYork':row['newYork'],'processing':'succeeded',
                       'syntheticDisclosureRequested':bool(item.get('syntheticDisclosureSentAt')),'syntheticDisclosureReadback':v['status'].get('containsSyntheticMedia')})
    scheduled=[v for v in after['videos'] if v['status'].get('publishAt') and parse(v['status']['publishAt'])>dt.datetime.now(UTC)]
    expected_future=[i for i in state['items'].values() if parse(i['row']['publishAt'])>dt.datetime.now(UTC)]
    assert {v['id'] for v in scheduled}=={i['videoId'] for i in expected_future}
    stamps=[v['status']['publishAt'] for v in scheduled]
    assert len(stamps)==len(set(stamps))==len(expected_future)
    receipt={'checkedAt':u.now(),'channelId':u.EXPECTED_CHANNEL_ID,'cadence':state['cadence'],'newUploads':6,'rescheduledExisting':len(old_order(state)),
             'previousVideosWithUnchangedStatus':len(before_by)-len(old_order(state)),'capturedBaselineDistinctVideos':len(before_by),
             'channelDistinctVideos':len(actual),'allCapturedPreviousTitlesDescriptionsTagsPreserved':True,'scheduled':checks}
    save(A/'qa/youtube-verification.json',receipt);save(R/'publication-receipt.json',receipt)
    state['verifiedAt']=u.now();save(STATE,state)
    queue=load(QUEUE)
    queue.update(lastVerifiedAt=u.now(),lastMixedBatch='v18-return-and-explore',scheduleTimezone='UTC')
    queue.setdefault('events',[]).append({'at':u.now(),'event':'mixed_batch_verified','newUploads':6,'scheduledTotal':len(state['order']),'receipt':str(R/'publication-receipt.json')})
    save(QUEUE,queue)
    print('VERIFIED: six new Shorts; fresh gameplay mixed into native UTC schedules; prior content preserved',flush=True)

def verify_partial(y,state):
    known=[i['videoId'] for i in state['items'].values() if i.get('videoId')]
    actual=fetch(y,known);checks=[];pending=[]
    for eid in state['order']:
        item=state['items'][eid]
        if not item.get('videoId'):
            pending.append({'id':eid,'file':item['row']['file'],'publishAt':item['row']['publishAt']});continue
        v=actual[item['videoId']]
        assert v['status']['privacyStatus']=='private' and v['status'].get('publishAt')==item['row']['publishAt']
        assert v['processingDetails']['processingStatus']=='succeeded'
        checks.append({'id':eid,'new':item['new'],'videoId':v['id'],'title':v['snippet']['title'],'url':'https://youtube.com/shorts/'+v['id'],
                       'publishAt':item['row']['publishAt'],'newYork':item['row']['newYork'],'processing':'succeeded'})
    receipt={'checkedAt':u.now(),'channelId':u.EXPECTED_CHANNEL_ID,'cadence':state['cadence'],'newUploads':sum(i['new'] for i in checks),
             'rescheduledExisting':len(old_order(state)),'scheduled':checks,'pendingUploads':pending,'nextUploadAttemptAt':state.get('nextUploadAttemptAt'),
             'continuationAutomationId':state.get('continuationAutomationId')}
    after=snapshot(y);save(A/'qa/youtube-partial-after.json',after)
    all_actual={v['id']:v for v in after['videos']};before=baseline()
    moved={state['items'][eid]['videoId'] for eid in old_order(state)}
    for old in before['videos']:
        v=all_actual[old['id']]
        for field in ['title','description','tags']:assert v['snippet'].get(field)==old['snippet'].get(field)
        if old['id'] not in moved:assert v['status']==old['status']
        else:assert {k:x for k,x in v['status'].items() if k!='publishAt'}=={k:x for k,x in old['status'].items() if k!='publishAt'}
    receipt['allPreviousTitlesDescriptionsTagsPreserved']=True
    receipt['previousVideosWithUnchangedStatus']=len(before['videos'])-len(moved)
    save(A/'qa/youtube-partial-verification.json',receipt);save(R/'publication-partial-receipt.json',receipt)
    print('VERIFIED PARTIAL',len(checks),'native schedules;',len(pending),'waiting for channel upload limit',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','publish','schedule','partial','verify-partial','verify']);args=ap.parse_args()
    if args.action=='prepare':prepare()
    else:
        y=u.get_youtube(open_browser=False);u.assert_pingblip(u.whoami(y),for_upload=True);state=load(STATE)
        if args.action=='publish':upload(y,state);schedule(y,state)
        elif args.action=='schedule':schedule(y,state)
        elif args.action=='partial':schedule(y,state);verify_partial(y,state);raise SystemExit(0)
        elif args.action=='verify-partial':verify_partial(y,state);raise SystemExit(0)
        verify(y,state)
