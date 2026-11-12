"""Verify the real action chain and the new source recording."""
import hashlib,json
from capture import A,P,R,Q
load=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=load(Q/'capture-summary.json')
assert c['completed'] and c['freshSession'] and c['newProfileCreated'] and c['noAdminAccess']
assert c['frames']>500
receipts={}
for name in ['hatch','starter_feed','house_claim','lisbon_scan','lisbon_catch','caught_feed','reykjavik_scan','reykjavik_catch']:
 d=load(Q/(name+'-result.json'));r=d['result'];receipts[name]=r
 assert d['httpStatus']==200 and d['recordedAt']>=c['recordingStartUnix']
 assert r.get('ok') if '_scan' not in name else bool(r['roster'])
assert not receipts['hatch'].get('already') and receipts['hatch']['creature']['feedCount']==0
assert receipts['starter_feed']['creature']['id']==receipts['hatch']['creature']['id']
assert receipts['starter_feed']['creature']['feedCount']==1
assert receipts['caught_feed']['creature']['id']==receipts['lisbon_catch']['creature']['id']
assert receipts['caught_feed']['creature']['feedCount']==1
for city in ['lisbon','reykjavik']:
 catch=receipts[city+'_catch'];assert not catch.get('already')
 assert any(r['id']==catch['creature']['speciesId'] and not r['owned'] for r in receipts[city+'_scan']['roster'])
initial=load(Q/'initial-owned.json');final=load(Q/'final_bench.json')
assert len(initial['creatures'])==1 and len(final['creatures'])==3
assert final['creditsMilli']==initial['creditsMilli']+250-2*50-2*30-2*80
assert load(Q/'house_bench.json')['creditsMilli']-load(Q/'starter_fed_bench.json')['creditsMilli']==250
raw=R/'capture/raw-vertical.mp4';raw_sha=sha(raw)
prior=load(P/'v19-next-meals/final/manifest.json')
prior_shas={s['sha256'] for e in prior for s in e['sources']}
assert raw_sha not in prior_shas
manifest=load(R/'final/manifest.json')
assert len(manifest)==6 and len({e['sha256'] for e in manifest})==6
for e in manifest:
 assert e['freshGameplay'] and e['sources'][0]['sha256']==raw_sha
 for source in e['sources']:assert sha(__import__('pathlib').Path(source['file']))==source['sha256']
report={'checkedAt':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'freshRecording':True,'newPublicFilmingProfile':True,'recordingStartUnix':c['recordingStartUnix'],'frames':c['frames'],'sourceSha256':raw_sha,'actualHatches':1,'actualFeeds':2,'actualDailyGrants':1,'actualScans':2,'actualNewCatches':2,'initialPips':initial['creditsMilli'],'finalPips':final['creditsMilli'],'noEarlierFootage':True,'noAdminAccess':True,'remoteCoordinates':{'Lisbon':[38.7223,-9.1393],'Reykjavik':[64.1466,-21.9426]}}
(A/'qa/freshness-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('Verified fresh recording: one hatch, two feeds, daily grant, two scans and two catches; pips balance reconciled')
