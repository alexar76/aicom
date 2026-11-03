"""Build the viewing copy and save the verified publication receipt."""
import json, subprocess
from publish import A, P, R, NEW_ORDER, load, save

receipt=load(A/'qa/youtube-verification.json')
assert receipt['newUploads']==6 and len(receipt['scheduled'])==12
manifest=load(R/'final/manifest.json')
args=['ffmpeg','-v','error','-y']
filters=[];inputs=[]
for i,eid in enumerate(NEW_ORDER):
    ep=next(e for e in manifest if e['id']==eid)
    args+=['-i',str(P/ep['file'])]
    filters.extend([f'[{i}:v]scale=540:960,setsar=1,setpts=PTS-STARTPTS[v{i}]',f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]'])
    inputs.append(f'[v{i}][a{i}]')
filters.append(''.join(inputs)+'concat=n=6:v=1:a=1[v][a]')
preview=R/'new-series-preview.mp4'
subprocess.run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-crf','22','-preset','veryfast','-threads','2','-c:a','aac','-b:a','128k','-movflags','+faststart',str(preview)],check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(preview),'-f','null','-'],check=True)

table=['| Date (UTC) | Time | ID | Video |','|---|---|---|---|']
for row in receipt['scheduled']:
    day,clock=row['publishAt'].rstrip('Z').split('T')
    table.append(f"| {day} | {clock[:5]} | {row['id']} | [{row['title']}]({row['url']}) |")
text='''# PingBlip — new friends and mixed queue, 31 October 2026

Six reviewed additions: two new edits of existing real gameplay, three new
character compositions using the approved game model renders, and one
previously unpublished supplied Sprinkle Moth clip with revised closing copy.
These are new edits; no fresh in-game session was captured in this batch.

Vertical 1080×1920, 30 fps, H.264/AAC. English captions, supplied PingBlip music,
no voiceover. Profile-link invitations and accurate source disclosures are
included. Gameplay waiting is marked as shortened. The six media files were
fully decoded and six frames from each were visually reviewed; loudness is
approximately −14 LUFS. Implementation and QA evidence remain in aicom.

The new items alternate with the six remaining scheduled videos. Native YouTube
publication is fixed at 13:00 and 19:00 UTC, two videos daily, including across
the America/New_York daylight-saving change. Audience reference dates/times
are preserved in publication-plan.json. Published videos were preserved.

'''
text+='\n'.join(table)+'\n\n'
text+=f"Verified through the YouTube API at {receipt['checkedAt']}. All twelve native publication timestamps match; all uploads processed successfully. All previous titles, descriptions and tags are unchanged. The six previous queued items only received new publishAt values.\n\n"
text+='[Preview the six additions](new-series-preview.mp4). [Publication receipt](publication-receipt.json).\n'
(R/'README.md').write_text(text)
local='''# PingBlip batch — 31 October 2026

Completed the user-authorized creation and scheduling of six additional Shorts.
The official channel guard verified @PingBlip / UCdhqQ5UAdUHPyX8BnolB4dQ.
Six new additions alternate with the six remaining private scheduled videos,
31 October–5 November 2026 at 13:00 and 19:00 UTC. Native YouTube scheduling
and completed processing were read back through the API.

Media, publication plan and receipt:
../PromoMaterials/blip/youtube-season-something-pinged/v16-new-friends/

PB47 and PB48 are new edits of preserved real hatch/catch recordings, not fresh
game sessions. PB49, PB50 and PB51 are new character compositions; CL21 is a
previously unused supplied clip with revised closing captions. All six final
contact sheets were reviewed. qa/validation.json records dimensions, complete
decoding, hashes and measured loudness. qa/youtube-verification.json records
all twelve verified native schedules. No GitHub writes occurred.

Fresh gameplay recording was considered but automatic approval review rejected
the legacy recorder because it retrieves an administrator password through
SSH/docker. That recorder did not run, and no such credential access occurred.
The rejected method was not retried; the completed media use existing local
sources without game server access.
'''
(A/'README.md').write_text(local)
root=P/'README.md';old=root.read_text()
start=old.index('Updated ');end=old.index('\n\n',start)
opening='Updated 2026-10-31. Current pack: `v16-new-friends/`, six additions alternating with six existing scheduled Shorts. Publish **two videos daily at 13:00 and 19:00 UTC**, fixed across daylight-saving changes. Audience reference: America/New_York. Current native queue: **October 31–November 5**. All twelve schedules and successful processing verified in `v16-new-friends/publication-receipt.json`. The new gameplay stories are edits of existing recordings; the pack also includes three new character compositions and one previously unpublished supplied clip. This cadence supersedes historical scheduling notes below.'
root.write_text(old[:start]+opening+old[end:])
print('Preview and receipts saved:',preview)
