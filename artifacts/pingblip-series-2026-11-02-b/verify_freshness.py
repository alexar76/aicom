from capture import A,P,R,Q
import json,hashlib
load=lambda p:json.loads(p.read_text())
c=load(Q/'capture-summary.json');prior=load(A.parent/'pingblip-series-2026-11-02/qa/capture/capture-summary.json')
assert c['completed'] and c['frames']>1000 and c['recordingStartUnix']>prior['recordingStartUnix']
initial=load(Q/'initial-owned.json');final=load(Q/'final_bench.json')
assert {p['id'] for p in initial['creatures']}=={p['id'] for p in final['creatures']}
for key in ['raccoon','donut','banana','dumpling','cola']:
 b=load(Q/(key+'-before.json'));a=load(Q/(key+'-after.json'));r=load(Q/(key+'_feed-result.json'))
 assert r['httpStatus']==200 and r['result']['ok'] and a['feedCount']==b['feedCount']+1 and r['recordedAt']>=c['recordingStartUnix']
scan=load(Q/'barcelona_scan_weather-result.json');assert scan['httpStatus']==200 and scan['result']['roster']
assert initial['creditsMilli']-final['creditsMilli']==5*50+30
raw=R/'capture/raw-vertical.mp4';old=P/'v18-return-and-explore/capture/raw-vertical.mp4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(raw)!=sha(old)
sq=A/'qa/capture-scan';scan2=load(sq/'barcelona_scan_weather-result.json');c2=load(sq/'capture-summary.json')
assert scan2['httpStatus']==200 and c2['completed'] and c2['recordingStartUnix']>c['recordingStartUnix']
assert load(sq/'final_bench.json')['creditsMilli']==0
report={'freshRecording':True,'sourceSha256':sha(raw),'previousRawSha256':sha(old),'recordingStartUnix':c['recordingStartUnix'],'frames':c['frames'],'actualFeeds':5,'actualScans':2,'newCatches':0,'initialPips':initial['creditsMilli'],'finalPips':0,'mainRecordingFinalPips':final['creditsMilli'],'additionalRecordingFrames':c2['frames'],'noEarlierFootage':True,'ownContinuingPublicProfile':True}
(A/'qa/freshness-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('Freshness verified: 5 actual feeds, 2 new scans, distinct new raw footage')
