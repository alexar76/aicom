"""Preview and receipts for the completed, freshly recorded gameplay batch."""
import subprocess
from publish import A,P,R,NEW_ORDER,load

complete=(A/'qa/youtube-verification.json').exists()
receipt=load(A/('qa/youtube-verification.json' if complete else 'qa/youtube-partial-verification.json'))
state=load(A/'qa/publication-state.json')
manifest=load(R/'final/manifest.json')
capture=load(A/'qa/capture/capture-summary.json')
assert len(manifest)==6 and all(e['freshGameplay'] for e in manifest)
args=['ffmpeg','-v','error','-y'];filters=[];inputs=[]
for i,eid in enumerate(NEW_ORDER):
    ep=next(e for e in manifest if e['id']==eid)
    args+=['-i',str(P/ep['file'])]
    filters.extend([f'[{i}:v]scale=540:960,setsar=1,setpts=PTS-STARTPTS[v{i}]',f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]'])
    inputs.append(f'[v{i}][a{i}]')
filters.append(''.join(inputs)+'concat=n=6:v=1:a=1[v][a]')
preview=R/'fresh-gameplay-preview.mp4'
subprocess.run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-crf','22','-preset','veryfast','-threads','2','-c:a','aac','-b:a','128k','-movflags','+faststart',str(preview)],check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(preview),'-f','null','-'],check=True)
table=['| Date (UTC) | Time | ID | Fresh session | Video |','|---|---|---|---|---|']
scheduled={row['id']:row for row in receipt['scheduled']}
for eid in state['order']:
    item=state['items'][eid]
    row=scheduled.get(eid,{**item['row'],'new':True,'url':None})
    day,clock=row['publishAt'].rstrip('Z').split('T')
    video=f"[{row['title']}]({row['url']})" if row['url'] else row['title']+' — ready, awaiting channel upload limit'
    table.append(f"| {day} | {clock[:5]} | {row['id']} | {'yes' if row['new'] else 'existing queue'} | {video} |")
text='''# PingBlip — fresh gameplay, 31 October 2026

The user explicitly requested freshly recorded game scenes. All six new Shorts
use only this batch's new live PingBlip recording. No footage from earlier packs
or promotional model animations is used in these additions.

- PB52: a new Dumpster Raccoon hatch.
- PB53: its first real feed, 0/5 to 1/5.
- PB54: the daily 250-pip house grant through the normal game button.
- PB55: a fresh Amsterdam scan and successful Glaze Donut catch.
- PB56: the newly caught Glaze Donut's first feed, 0/5 to 1/5.
- PB57: a fresh Tokyo scan and successful Bruised Banana catch.

Map coordinates were typed; the videos do not claim physical travel. Results
are examples, not guaranteed hatches/catches. All actions succeeded through the
public game interface, with no administrator credentials, SSH, game-state
modification, invented results, cooldown skipping or evolution staging.

The new browser explicitly identifies itself as HeadlessChrome / Playwright,
which the existing game code classifies as automation and excludes from its
conversion funnel. No administrator/test cookie was obtained. Session state is
private temporary runtime data; publication materials contain no session tokens.

'''
text+=f"Recording completed {capture['recordedAtUtc']}; {capture['frames']:,} original frames were preserved in capture/frames. Full raw recording: capture/raw-vertical.mp4. Action timestamps, HTTP responses, before/after game state, shot offsets and source hashes are preserved in the aicom implementation/QA folder and final/manifest.json.\n\n"
text+='The Shorts retain our vertical 1080×1920, 30 fps format, large English captions, supplied PingBlip music and no voiceover. Waiting is shortened and labelled. All six files were fully decoded, audio levels measured, and six frames from each reviewed visually.\n\n'
text+=f"The complete plan alternates six new videos with {receipt['rescheduledExisting']} private scheduled items from the existing queue. Publication slots remain fixed at **13:00 and 19:00 UTC**, including across the America/New_York daylight-saving change. Already published videos are preserved.\n\n"
if not complete:
    text+=f"**Current status: four new uploads and fourteen native schedules verified. PB56 and PB57 are complete local files but are not yet uploaded: YouTube returned uploadLimitExceeded. Their reserved slots are 5 and 6 November at 13:00 UTC. One-time continuation automation `pingblip-2` is scheduled for 1 November 2026, 20:30 UTC (21:30 Europe/Amsterdam), after the 24-hour wait. Keep the computer on and Codex running for the local continuation. The original `pingblip` monitor remains paused.**\n\n"
text+='\n'.join(table)+'\n\n'
receipt_name='publication-receipt.json' if complete else 'publication-partial-receipt.json'
text+=f"{'All sixteen' if complete else 'Fourteen accepted'} native timestamps and successful processing verified through the YouTube API at {receipt['checkedAt']}. [Publication receipt]({receipt_name}). [Preview all six fresh videos](fresh-gameplay-preview.mp4).\n"
(R/'README.md').write_text(text)
(A/'README.md').write_text('''# Fresh PingBlip gameplay — 31 October 2026

Six Shorts made from a newly recorded live game session and reviewed visually.
No earlier
gameplay footage was reused. The public HeadlessChrome / Playwright browser used
ordinary game controls and no administrator credentials, SSH or old player tokens.
The recognized automation UA is excluded by the game's existing funnel logic.

Media and receipts: ../PromoMaterials/blip/youtube-season-something-pinged/v17-fresh-gameplay/

capture.py preserves original frames and successful hatch/feed/grant/scan/catch
responses with fresh timestamps. build.py refuses recordings predating this user
request and uses only the fresh raw capture as its video source. qa/validation.json
records hashes, stream checks, complete decoding, audio measurements and visual
review. qa/youtube-verification.json records the verified native schedule.

The prior batch remains historical. Published videos were not replaced/deleted.
Only private scheduled videos were moved into the new mix. No GitHub writes occurred.
''')
(A/'README.md').write_text((A/'README.md').read_text()+('\nAll six uploads and sixteen planned publications verified.\n' if complete else '''
Current partial status: PB52–PB55 uploaded and scheduled; fourteen native
publication times verified. PB56 and PB57 remain ready local files after YouTube
returned uploadLimitExceeded on PB56. They have no video ID yet. Their intended
slots are 5 and 6 November at 13:00 UTC. One-time continuation `pingblip-2` is
scheduled for 1 November 2026 at 20:30 UTC / 21:30 Europe/Amsterdam. The original
`pingblip` monitor remains PAUSED. The computer and Codex must be running.

After the saved nextUploadAttemptAt gate, resume with:
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=ignore python3 artifacts/pingblip-fresh-gameplay-2026-10-31/publish.py publish
The publisher skips known uploaded IDs and handles naturally public past slots.
After successful verification, run finalize.py and disable only pingblip-2.
'''))
root=P/'README.md';old=root.read_text();start=old.index('Updated ');end=old.index('\n\n',start)
first=state['items'][state['order'][0]]['row']['publishAt'][:10];last=state['items'][state['order'][-1]]['row']['publishAt'][:10]
opening=f"Updated {receipt['checkedAt'][:10]}. Current pack: `v17-fresh-gameplay/`, **six newly recorded live-gameplay Shorts**, mixed with {receipt['rescheduledExisting']} existing private queued items. All six additions use the fresh 31 October session. Planned queue: **{first}–{last}**, daily slots at **13:00 and 19:00 UTC**, fixed across daylight-saving changes. Audience reference: America/New_York. "
opening+=(f"All sixteen native schedules verified in `v17-fresh-gameplay/publication-receipt.json`. " if complete else "Four new uploads and fourteen native schedules are verified. PB56/PB57 are ready but await the channel's daily upload limit; one-time retry is set for 1 November at 20:30 UTC. See `v17-fresh-gameplay/publication-partial-receipt.json`. ")
opening+='This cadence supersedes historical scheduling notes below.'
root.write_text(old[:start]+opening+old[end:])
print('Fresh preview and receipts saved:',preview)
