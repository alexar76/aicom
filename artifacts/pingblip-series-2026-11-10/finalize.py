"""Create the November 10 preview and factual production/publication receipts."""
import hashlib
import json
import re
import subprocess
import sys

from capture import A, P, R

ORDER = [f'PB{number}' for number in range(76, 82)]


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preview(episodes):
    target = R / 'series-preview.mp4'
    state_path = R / 'series-preview-state.json'
    signature = [{'id': episode['id'], 'file': episode['file'], 'sha256': episode['sha256']}
                 for episode in episodes]
    for episode in episodes:
        assert sha(P / episode['file']) == episode['sha256']
    if target.exists() and state_path.exists():
        previous = load(state_path)
        if previous.get('sources') == signature and previous.get('sha256') == sha(target):
            return target
    args = ['ffmpeg', '-v', 'error', '-y']
    filters, parts = [], []
    for index, episode in enumerate(episodes):
        args += ['-i', str(P / episode['file'])]
        filters += [f'[{index}:v]scale=540:960,setsar=1,setpts=PTS-STARTPTS[v{index}]',
                    f'[{index}:a]aresample=48000,asetpts=PTS-STARTPTS[a{index}]']
        parts.append(f'[v{index}][a{index}]')
    filters.append(''.join(parts) + 'concat=n=6:v=1:a=1[v][a]')
    temporary = R / 'series-preview.rendering.mp4'
    subprocess.run(args + ['-filter_complex_threads', '1', '-filter_complex', ';'.join(filters),
                           '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '22',
                           '-preset', 'veryfast', '-threads', '2', '-c:a', 'aac', '-b:a', '128k',
                           '-movflags', '+faststart', str(temporary)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(temporary), '-f', 'null', '-'], check=True)
    temporary.replace(target)
    state_path.write_text(json.dumps({'sources': signature, 'sha256': sha(target)}, indent=2) + '\n')
    return target


def main():
    manifest = load(R / 'final/manifest.json')
    assert len(manifest) == 6 and {episode['id'] for episode in manifest} == set(ORDER)
    episodes = [next(episode for episode in manifest if episode['id'] == eid) for eid in ORDER]
    target = preview(episodes)
    if '--preview-only' in sys.argv:
        print('Saved preview:', target)
        return
    receipt = load(A / 'qa/youtube-verification.json')
    capture = load(A / 'qa/capture/capture-summary.json')
    freshness = load(A / 'qa/freshness-verification.json')
    assert receipt['newUploads'] == 6 and receipt['rescheduledExisting'] == 0
    assert receipt['allPreviousPublicationSchedulesPreserved']
    assert receipt['allCapturedPreviousTitlesDescriptionsTagsPreserved']
    assert all(episode['freshGameplay'] and episode['visualApproved'] for episode in episodes)
    assert {row['id'] for row in receipt['scheduled']} == set(ORDER)
    assert capture['resumedOwnFilmingProfile'] and capture['newProfileCreated'] is False
    assert freshness['actualFeeds'] == 3 and freshness['actualDailyGrants'] == 1 and freshness['actualNewCatches'] == 2
    future = sorted(receipt['futureQueue'], key=lambda row: row['publishAt'])
    assert future and len({row['publishAt'] for row in future}) == len(future)
    new_rows = [next(row for row in receipt['scheduled'] if row['id'] == eid) for eid in ORDER]
    first_new, last_new = new_rows[0]['publishAt'][:10], new_rows[-1]['publishAt'][:10]
    first_queue, last_queue = future[0]['publishAt'][:10], future[-1]['publishAt'][:10]
    text = '# PingBlip — Next Stop, 10 November 2026\n\n'
    text += ('Six new gameplay Shorts recorded on 10 November 2026 using our continuing public filming profile from the 9 November batch. '
             'The original three creature IDs and 430-pip balance were checked before recording. All footage in this batch is newly captured.\n\n')
    for episode in episodes:
        text += f"- {episode['id']}: {episode['note']}\n"
    text += (f"\nRecording finished {capture['recordedAtUtc']}; {capture['frames']:,} original frames are retained under capture/frames, "
             'with capture/raw-vertical.mp4. Public response receipts, before/after bench states, source hashes and timestamps are retained in '
             'aicom/artifacts/pingblip-series-2026-11-10/qa.\n\n')
    text += (f"The verified action chain contains three feeds, one actual 250-pip daily grant, {freshness['actualScans']} paid scans and two new catches. "
             f"The bench grows from {freshness['initialOwnedCreatures']} to {freshness['finalOwnedCreatures']} creatures; "
             f"the balance reconciles from {freshness['initialPips']} to {freshness['finalPips']} in-game pips. "
             'Pips are game credits, not money.\n\n')
    text += ('The recording used normal public game controls and an honest automation user agent. The documented filming profile was resumed; no new player profile was created. '
             'Kyoto and Cape Town coordinates were typed into the public map for remote gameplay. This does not claim physical travel. '
             'Map layer choices and all paid scan attempts are preserved in the evidence. Waiting is shortened in edits. '
             'The creatures shown are examples, not guaranteed hatches or finds. No administrator access or invented outcomes were used.\n\n')
    text += ('Format: 1080×1920, 30 fps, H.264/AAC, large English captions, supplied original AI-generated PingBlip music and no voiceover. '
             'Full decoding, audio measurements, source hashes, timing and final visual review are recorded in QA.\n\n')
    text += (f"The six additions occupy {first_new}–{last_new}, appended after the previous queue. Native publication slots remain **13:00 and 19:00 UTC**, "
             'fixed across daylight-saving changes; America/New_York is the audience reference. '
             f"At verification, the complete future queue contained **{len(future)} videos, {first_queue}–{last_queue}**. "
             'Preexisting metadata, status settings and publication schedules were preserved.\n\n')
    text += '| Date (UTC) | Time | ID | New video |\n|---|---|---|---|\n'
    for row in new_rows:
        text += f"| {row['publishAt'][:10]} | {row['publishAt'][11:16]} | {row['id']} | [{row['title']}]({row['url']}) |\n"
    text += f"\nNative timestamps and successful processing verified at {receipt['checkedAt']}. [Publication receipt](publication-receipt.json). [Series preview](series-preview.mp4).\n"
    (R / 'README.md').write_text(text)
    (A / 'README.md').write_text(
        '# PingBlip continuing series — 10 November 2026\n\n'
        'PB76–PB81: newly recorded gameplay from our documented own filming profile, reviewed, uploaded to the guarded official @PingBlip channel and appended in native 13:00/19:00 UTC slots. '
        'Technical scripts and QA remain here; media, editable caption files, preview and publication receipt are in ../PromoMaterials/blip/youtube-season-something-pinged/v21-next-stop/.\n\n'
        'qa/youtube-before.json and qa/youtube-after.json retain API evidence; qa/youtube-verification.json records the new schedules, full future queue and preservation of previous videos. '
        'qa/validation.json and qa/freshness-verification.json record media checks and actual game outcomes, including the previous-profile identity match, three feeds, daily grant, all paid scans and two new catches.\n')
    root = P / 'README.md'
    existing = root.read_text()
    opening = (f"Updated {receipt['checkedAt'][:10]}. Current pack: `v21-next-stop/`, **six fresh gameplay Shorts recorded on 10 November**, "
               f"appended at **{first_new}–{last_new}**. The verified future native queue contains **{len(future)} videos, {first_queue}–{last_queue}**, "
               'two daily at **13:00 and 19:00 UTC**, fixed across daylight-saving changes; America/New_York is the audience reference. '
               'All six new timestamps and completed processing are verified in `v21-next-stop/publication-receipt.json`; previous video metadata and native schedules were preserved. '
               'This cadence supersedes historical scheduling notes below.')
    match = re.search(r'^Updated [^\n]*(?:\n(?!\n)[^\n]+)*', existing, re.MULTILINE)
    assert match, 'Preserve the existing README and inspect its current-summary location'
    root.write_text(existing[:match.start()] + opening + existing[match.end():])
    print('Saved', target, 'and publication documentation;', len(future), 'future videos,', first_queue, 'through', last_queue)


if __name__ == '__main__':
    main()
