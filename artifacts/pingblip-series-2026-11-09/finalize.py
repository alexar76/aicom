"""Create a series preview and truthful production/publication documentation."""
import json,subprocess,sys
from pathlib import Path
from capture import A,P,R
ORDER=[f'PB{x}' for x in range(70,76)]
load=lambda p:json.loads(p.read_text())
eps=load(R/'final/manifest.json')
args=['ffmpeg','-v','error','-y'];filters=[];parts=[]
for i,eid in enumerate(ORDER):
    e=next(e for e in eps if e['id']==eid);args+=['-i',str(P/e['file'])]
    filters += [f'[{i}:v]scale=540:960,setsar=1,setpts=PTS-STARTPTS[v{i}]',f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]']
    parts.append(f'[v{i}][a{i}]')
preview=R/'series-preview.mp4'
if not preview.exists():
    filters.append(''.join(parts)+'concat=n=6:v=1:a=1[v][a]')
    subprocess.run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-crf','22','-preset','veryfast','-threads','2','-c:a','aac','-b:a','128k','-movflags','+faststart',str(preview)],check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(preview),'-f','null','-'],check=True)
if '--preview-only' in sys.argv:raise SystemExit(0)
r=load(A/'qa/youtube-verification.json');c=load(A/'qa/capture/capture-summary.json')
assert r['newUploads']==6 and all(e['freshGameplay'] and e['visualApproved'] for e in eps)
text='# PingBlip — New Signal, 9 November 2026\n\nSix new gameplay Shorts, recorded in one fresh public filming profile on 9 November 2026. The temporary sessions from earlier batches were absent, so this is a new story, not a continuation of their creature progression. No earlier gameplay footage is used.\n\n'
for e in eps:text+=f"- {e['id']}: {e['note']}\n"
text+=f"\nRecording finished {c['recordedAtUtc']}; {c['frames']:,} original captured frames are retained under capture/frames, with capture/raw-vertical.mp4. Technical evidence and successful public game responses are retained in aicom/artifacts/pingblip-series-2026-11-09/qa.\n\n"
text+='The recording used the normal public game UI, an honest automation user agent and one newly created filming profile. No administrator access or invented game outcomes. Coordinates for Lisbon and Reykjavik were typed into the map for remote play; this does not claim physical travel. Waiting is shortened in edits. The creatures shown are examples, not guaranteed hatches or finds.\n\n'
text+='Format: 1080×1920, 30 fps, H.264/AAC, large English captions, provided original AI-generated PingBlip music and no voiceover. Full decoding, audio measurements, hashes, source timing and final visual review are documented in QA.\n\n'
text+='The six new videos were appended after the existing queue. Fixed publication slots are 13:00 and 19:00 UTC (America/New_York audience reference). Previously uploaded videos and their native schedules were preserved.\n\n'
text+='| Date (UTC) | Time | ID | Video |\n|---|---|---|---|\n'
for v in r['scheduled']:
    text+=f"| {v['publishAt'][:10]} | {v['publishAt'][11:16]} | {v['id']} | [{v['title']}]({v['url']}) |\n"
text+=f"\nNative schedules and successful processing verified at {r['checkedAt']}. [Publication receipt](publication-receipt.json). [Series preview](series-preview.mp4).\n"
(R/'README.md').write_text(text)
(A/'README.md').write_text('# PingBlip fresh series — 9 November 2026\n\nPB70–PB75: fresh public gameplay, captured and visually reviewed, uploaded to the guarded official @PingBlip channel and appended in native 13:00/19:00 UTC slots. Technical scripts and QA remain here; media, editable caption files, preview and publication receipt are in ../PromoMaterials/blip/youtube-season-something-pinged/v20-new-signal/.\n\nqa/youtube-before.json and qa/youtube-after.json preserve API evidence; qa/youtube-verification.json records new schedules and preservation of earlier videos. qa/validation.json and qa/freshness-verification.json record media checks and actual game outcomes.\n')
root=P/'README.md';s=root.read_text();start=s.index('Updated ');end=s.index('\n\n',start)
first=r['scheduled'][0]['publishAt'][:10];last=r['scheduled'][-1]['publishAt'][:10]
opening=f"Updated {r['checkedAt'][:10]}. Current pack: `v20-new-signal/`, **six fresh gameplay Shorts recorded on 9 November**, appended to the existing native queue at **{first}–{last}**, two daily at **13:00 and 19:00 UTC**. Fixed UTC across daylight-saving changes; America/New_York is the audience reference. Successful processing and all six timestamps are verified in `v20-new-signal/publication-receipt.json`; previous video metadata and schedule were preserved. This cadence supersedes historical scheduling notes below."
root.write_text(s[:start]+opening+s[end:])
print('Saved',preview, 'and publication documentation')
