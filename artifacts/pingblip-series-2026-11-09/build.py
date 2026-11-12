"""Build PB70–PB75 only from the newly recorded 9 November gameplay.

The capture must complete before this script runs. Names, balances and progress
come from successful public game responses, never from a planned outcome.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys

from PIL import Image, ImageDraw
from capture import A, P, R, Q as CAPTURE_Q

W, F, Q = A / 'work', R / 'final', A / 'qa'
spec = importlib.util.spec_from_file_location('style', P / 'v14-action-first/source/build_batch.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


@lru_cache(maxsize=40)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(name, scan=False):
    data = load(CAPTURE_Q / (name + '-result.json'))
    summary = load(CAPTURE_Q / 'capture-summary.json')
    assert data['httpStatus'] == 200
    assert data['recordedAt'] >= summary['recordingStartUnix'], 'Action predates this recording'
    assert data['result'].get('roster') if scan else data['result'].get('ok')
    return data['result']


def episodes():
    m = load(CAPTURE_Q / 'marks.json')
    hatch = receipt('hatch')
    feed = receipt('starter_feed')
    grant = receipt('house_claim')
    lisbon = receipt('lisbon_catch')
    caught_feed = receipt('caught_feed')
    reykjavik = receipt('reykjavik_catch')
    receipt('lisbon_scan', scan=True)
    receipt('reykjavik_scan', scan=True)
    assert not hatch['already'] and not lisbon['already'] and not reykjavik['already']
    assert feed['creature']['id'] == hatch['creature']['id']
    assert caught_feed['creature']['id'] == lisbon['creature']['id']
    assert feed['creature']['feedCount'] == caught_feed['creature']['feedCount'] == 1
    assert not feed.get('justEvolved') and not caught_feed.get('justEvolved')
    starter = hatch['species']['name']
    first = lisbon['species']['name']
    third = reykjavik['species']['name']
    amount = grant['grantedMilli']
    assert grant['kind'] == 'house' and amount > 0

    def shot(key, offset, dur, line, face=False, y=190):
        start = round(m[key] + offset, 3)
        assert start >= 0
        # Real-time cuts preserve the action; no simulated button press or state.
        return (start, dur, 1, line, y, face)

    return [
        dict(id='PB70', slug='first-signal', name=starter,
             title=f'One hatch. {starter}. We are roommates now.', duration=9.0, music_start=6.69,
             evidence=['hatch'], states=['initial-owned', 'starter_bench'],
             note=f'A new public filming profile, created for this recording on 9 November 2026. Its real free first hatch produced {starter}. The outcome shown is an example, not a guaranteed first pet.',
             shots=[shot('starter_bench', -2, 1.5, 'NEW PET. ZERO INTERVIEW.', face=True),
                    shot('hatch_click', -.7, 1.5, 'ONE FREE HATCH.', y=1325),
                    shot('hatch_reveal', 1.3, 2.5, starter.upper(), y=1325),
                    shot('starter_bench', -4, 3.5, 'WE LIVE TOGETHER NOW.', face=True)]),
        dict(id='PB71', slug='first-signal-first-meal', name=starter,
             title=f'{starter} moved in. The first snack was immediate.', duration=9.0, music_start=18,
             evidence=['starter_feed'], states=['starter_bench', 'starter_fed_bench'],
             note=f'The first successful feed of the newly hatched {starter}, captured on 9 November 2026. The real feed counter advances from 0/5 to 1/5; no evolution is shown.',
             shots=[shot('starter_bench', -2, 1.4, 'ROOMMATE HAS A REQUEST.', face=True),
                    shot('starter_feed_click', -.8, 1.6, 'BREAKFAST. RIGHT NOW.'),
                    shot('starter_feed_result', .15, 2.5, 'FIRST MEAL: DELIVERED.'),
                    shot('starter_fed_bench', -4, 3.5, 'ONE OF FIVE. GOOD START.')]),
        dict(id='PB72', slug='tiny-pet-serious-budget', name=starter,
             title=f'Tiny pet. {amount} game pips. A very serious budget.', duration=9.0, music_start=24,
             evidence=['house_claim'], states=['starter_fed_bench', 'house_bench'],
             note=f'The daily house grant was claimed through the normal public game button on 9 November 2026: {amount} in-game pips. The response and persisted bench balance show the actual grant. Pips are game credits, not money.',
             shots=[shot('house_bench', -2, 1.4, 'SMALL PET. BIG PLANS.', face=True),
                    shot('house_claim_click', -1.3, 1.6, f'{amount} FREE GAME PIPS.'),
                    shot('house_claim_result', .1, 2.5, 'ON THE HOUSE. CLAIMED.'),
                    shot('house_bench', -4, 3.5, 'NEXT: FIND A FRIEND.')]),
        dict(id='PB73', slug='lisbon-found-a-friend', name=first,
             title=f'Lisbon sent {first}. I brought it home.', duration=10.0, music_start=13,
             evidence=['lisbon_scan', 'lisbon_catch'], states=['house_bench', 'lisbon_bench'],
             note=f'A real weather-layer scan at typed Lisbon coordinates and a successful catch of {first}, recorded on 9 November 2026. This is remote map gameplay; it does not claim physical travel. The catch joins the new profile on its bench.',
             shots=[shot('lisbon_bench', -2, 1.4, 'LISBON SENT A FRIEND.', face=True),
                    shot('lisbon_coordinates', .1, 1.5, 'PIN DROPPED: LISBON.'),
                    shot('lisbon_roster', .1, 1.6, 'A REAL MAP SIGNAL.'),
                    shot('lisbon_catch_click', -.7, 1.8, 'THIS ONE. COMING HOME.'),
                    shot('lisbon_bench', -4.2, 3.7, first.upper())]),
        dict(id='PB74', slug='welcome-home-first-snack', name=first,
             title=f'{first} joined the bench. I handled the welcome snack.', duration=9.0, music_start=10,
             evidence=['lisbon_catch', 'caught_feed'], states=['lisbon_bench', 'caught_fed_bench'],
             note=f'The newly caught {first} receives its first successful feed in the same fresh recording on 9 November 2026. The catch and feed creature IDs match, and the persisted feed counter is 1/5. No evolution is claimed.',
             shots=[shot('lisbon_bench', -2, 1.4, 'NEW FRIEND. SAME RULES.', face=True),
                    shot('caught_feed_click', -.8, 1.6, 'WELCOME SNACK COMES FIRST.'),
                    shot('caught_feed_result', .15, 2.5, 'SNACK FIRST. FRIENDS NOW.'),
                    shot('caught_fed_bench', -4, 3.5, 'ONE OF FIVE. WELCOME HOME.')]),
        dict(id='PB75', slug='reykjavik-third-roommate', name=third,
             title=f'Reykjavik found {third}. The bench has three now.', duration=10.0, music_start=38.7,
             evidence=['reykjavik_scan', 'reykjavik_catch'], states=['caught_fed_bench', 'reykjavik_bench', 'final_bench'],
             note=f'A real weather-layer scan at typed Reykjavik coordinates and a successful catch of {third}, recorded on 9 November 2026. The new public filming profile ends with three owned creatures. Coordinates are entered for remote gameplay, not physical travel.',
             shots=[shot('reykjavik_bench', -2, 1.4, 'ONE MORE ROOMMATE.', face=True),
                    shot('reykjavik_coordinates', .1, 1.5, 'NEXT PIN: REYKJAVIK.'),
                    shot('reykjavik_roster', .1, 1.6, 'ANOTHER REAL SIGNAL.'),
                    shot('reykjavik_catch_click', -.7, 1.8, 'THIRD FRIEND. CAUGHT.'),
                    shot('final_bench', -4.2, 3.7, third.upper())]),
    ]


def build(ep):
    raw = R / 'capture/raw-vertical.mp4'
    clips = []
    assert abs(sum(s[1] for s in ep['shots']) - ep['duration']) < .001
    for n, (start, dur, speed, line, y, face) in enumerate(ep['shots']):
        card = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((35, y, 1045, y + 140), radius=24, fill=(10, 18, 24, 242))
        b.label(card, line, y + 39, b.CREAM, 55)
        # Safe title/CTA strips leave the middle of the real game evidence visible.
        d.rounded_rectangle((50, 1745, 1030, 1800), radius=9, fill=(6, 10, 12, 230))
        b.label(card, 'REAL PLAY · 09 NOV 2026 · WAITING SHORTENED', 1755, b.CREAM, 25)
        if n == len(ep['shots']) - 1:
            d.rounded_rectangle((65, 1620, 1015, 1690), radius=12, fill=(6, 10, 12, 230))
            b.label(card, 'GET YOUR PET · LINK IN PROFILE', 1634, b.LIME, 34)
        png = W / f'{ep["id"]}-{n}.png'
        card.save(png)
        clip = W / f'{ep["id"]}-{n}.mp4'
        if face == 'hatch':
            crop = 'crop=700:450:190:40,scale=1080:694,pad=1080:1920:0:580:color=0x060a0c,'
        elif face:
            crop = 'crop=900:650:90:400,scale=1080:780,pad=1080:1920:0:550:color=0x060a0c,'
        else:
            crop = ''
        b.run(['ffmpeg', '-v', 'error', '-y', '-ss', start, '-i', raw, '-loop', '1', '-i', png,
               '-filter_complex_threads', '1', '-filter_complex',
               f'[0:v]setpts=(PTS-STARTPTS)/{speed},{crop}fps=30,tpad=stop_mode=clone:stop_duration=2[v];[v][1:v]overlay=0:0,format=yuv420p[o]',
               '-map', '[o]', '-an', '-t', dur, '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-threads', '2', clip])
        clips.append(clip)
    concat = W / f'{ep["id"]}.ffconcat'
    concat.write_text('ffconcat version 1.0\n' + ''.join(f"file '{clip}'\n" for clip in clips))
    silent = W / f'{ep["id"]}-silent.mp4'
    b.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', concat, '-c', 'copy', silent])
    out = F / f'{ep["id"]}-{ep["slug"]}.mp4'
    music = b.mux(ep, silent, ep['duration'], out)
    sources = [raw, CAPTURE_Q / 'capture-summary.json', CAPTURE_Q / 'initial-owned.json',
               CAPTURE_Q / 'final_bench.json', CAPTURE_Q / 'marks.json', CAPTURE_Q / 'automation-classification.json']
    sources += [CAPTURE_Q / (name + '-result.json') for name in ep['evidence']]
    sources += [CAPTURE_Q / (name + '.json') for name in ep['states']]
    sources = list(dict.fromkeys(sources))
    desc = (ep['note'] + '\nWaiting shortened; all game footage comes from this new recording.\n\n'
            'Get your pet free through the game link on @PingBlip.\nhttps://pingblip.com/\n'
            'Your first creature is a surprise; the creatures and map results shown are examples.\n'
            'Game pips are in-game credits, not money.\n\nMusic: PingBlip original, AI-generated.\n'
            '#PingBlip #BrowserGame #CreatureCollector')
    row = {**ep, 'kind': 'gameplay', 'freshGameplay': True,
           'recordedAtUtc': load(CAPTURE_Q / 'capture-summary.json')['recordedAtUtc'],
           'file': str(out.relative_to(P)), 'description': desc, 'sha256': sha(out), 'musicEdit': music,
           'sources': [{'file': str(s), 'sha256': sha(s)} for s in sources], 'visualApproved': False}
    path = F / 'manifest.json'
    rows = load(path) if path.exists() else []
    rows = [r for r in rows if r['id'] != ep['id']] + [row]
    save(path, rows)
    out.with_suffix('.txt').write_text(ep['title'] + '\n\n' + desc + '\n')
    b.run(['ffmpeg', '-v', 'error', '-y', '-ss', '0.5', '-i', out, '-frames:v', '1', out.with_suffix('.jpg')])
    print('BUILT', ep['id'], ep['name'], ep['duration'], flush=True)


if __name__ == '__main__':
    for path in [W, F, Q]:
        path.mkdir(parents=True, exist_ok=True)
    summary = load(CAPTURE_Q / 'capture-summary.json')
    assert summary['completed'] and summary['freshSession'] and summary['newProfileCreated']
    for ep in episodes():
        if len(sys.argv) == 1 or ep['id'] in sys.argv[1:]:
            build(ep)
