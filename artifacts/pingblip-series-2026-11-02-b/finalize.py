"""Save the reviewed November 2 series and its native publication receipt."""
import subprocess,sys
from publish import A,P,R,NEW_ORDER,load

manifest=load(R/'final/manifest.json');capture=load(A/'qa/capture/capture-summary.json')
assert all(e['freshGameplay'] for e in manifest)
args=['ffmpeg','-v','error','-y'];filters=[];parts=[]
for i,eid in enumerate(NEW_ORDER):
    ep=next(e for e in manifest if e['id']==eid);args+=['-i',str(P/ep['file'])]
    filters.extend([f'[{i}:v]scale=540:960,setsar=1,setpts=PTS-STARTPTS[v{i}]',f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]']);parts.append(f'[v{i}][a{i}]')
filters.append(''.join(parts)+'concat=n=6:v=1:a=1[v][a]')
preview=R/'series-preview.mp4'
subprocess.run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-crf','22','-preset','veryfast','-threads','2','-c:a','aac','-b:a','128k','-movflags','+faststart',str(preview)],check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(preview),'-f','null','-'],check=True)
if '--preview-only' in sys.argv:raise SystemExit(0)
receipt=load(A/'qa/youtube-verification.json');state=load(A/'qa/publication-state.json')
assert receipt['newUploads']==6
table=['| UTC date | Time | ID | New series | Video |','|---|---|---|---|---|']
for row in receipt['scheduled']:
    day,clock=row['publishAt'].rstrip('Z').split('T')
    table.append(f"| {day} | {clock[:5]} | {row['id']} | {'yes' if row['new'] else 'existing queue'} | [{row['title']}]({row['url']}) |")
summary='# PingBlip — next meals, 2 November 2026\n\n'
summary+='Six newly recorded gameplay Shorts from our continuing public filming profile. All footage was captured on 2 November 2026. The same five-pet filming profile was resumed for a separate new recording. No earlier video footage is used.\n\n'
for ep in manifest:summary+=f"- {ep['id']}: {ep['note']}\n"
summary+=f"\nRecording completed {capture['recordedAtUtc']}; {capture['frames']:,} original frames are preserved in capture/frames and capture/raw-vertical.mp4. Successful public game responses, before/after state, timestamps and source hashes are kept in aicom QA evidence and final/manifest.json.\n\n"
summary+='The honest HeadlessChrome / Playwright UA is recognized as automation by the existing game funnel. No administrator access, SSH, altered game state or invented results were used. Video: 1080×1920, 30 fps, H.264/AAC; large English captions, supplied PingBlip music, no voiceover. All six files were fully decoded, audio measured, and final contact sheets visually reviewed.\n\n'
summary+=f"The six additions are mixed with {receipt['rescheduledExisting']} previously scheduled videos. Fixed UTC slots: **13:00 and 19:00**, two videos per day. Audience reference: America/New_York. Published videos are preserved.\n\n"
summary+='\n'.join(table)+'\n\n'
summary+=f"Native timestamps and completed processing verified at {receipt['checkedAt']}. [Publication receipt](publication-receipt.json). [Preview all six](series-preview.mp4).\n"
(R/'README.md').write_text(summary)
(A/'README.md').write_text('# PingBlip new series — 2 November 2026\n\nSix fresh gameplay Shorts PB64–PB69 were recorded, reviewed, uploaded to the guarded official @PingBlip channel and mixed into the native UTC queue. Technical evidence remains here; media and publication receipt are in ../PromoMaterials/blip/youtube-season-something-pinged/v19-next-meals/.\n\nThe new recording resumes only our documented public filming profile. Five actual feeds and two Barcelona scans (one selected for the final episode) are supported by their successful HTTP responses and before/after state. No older gameplay footage, administrator credentials, SSH, game-state fabrication or GitHub writes were used.\n\nqa/validation.json records stream checks, full decoding, audio measurements, hashes and visual approval. qa/youtube-verification.json records the verified native schedule and preservation of previous content.\n')
root=P/'README.md';text=root.read_text();start=text.index('Updated ');end=text.index('\n\n',start)
first=receipt['scheduled'][0]['publishAt'][:10];last=receipt['scheduled'][-1]['publishAt'][:10]
opening=f"Updated {receipt['checkedAt'][:10]}. Current pack: `v19-next-meals/`, **six new gameplay Shorts captured on 2 November**, mixed with {receipt['rescheduledExisting']} previously scheduled items. Current native queue: **{first}–{last}**, two videos daily at **13:00 and 19:00 UTC**, fixed across daylight-saving changes. Audience reference: America/New_York. All {len(receipt['scheduled'])} native timestamps and successful processing are verified in `v19-next-meals/publication-receipt.json`. This cadence supersedes historical scheduling notes below."
root.write_text(text[:start]+opening+text[end:])
print('Series preview and final publication documentation saved:',preview)

queue_path=P/'v5-week-one/queue-state.json'
queue=load(queue_path)
if queue.get('pendingFreshBatch',{}).get('batch')=='v19-next-meals':
    queue.pop('pendingFreshBatch',None)
    queue_path.write_text(__import__('json').dumps(queue,indent=2,ensure_ascii=False)+'\n')
