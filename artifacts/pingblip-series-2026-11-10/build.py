"""Build PB76–PB81 from the newly recorded 10 November continuing profile.

Titles, balances and progress are derived from successful public game receipts.
Only this batch's fresh recording is used; earlier footage remains untouched.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib.util
import json
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


@lru_cache(maxsize=50)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(name, scan=False):
    data = load(CAPTURE_Q / (name + '-result.json'))
    summary = load(CAPTURE_Q / 'capture-summary.json')
    assert data['httpStatus'] == 200, name
    assert data['recordedAt'] >= summary['recordingStartUnix'], 'Action predates this recording'
    result = data['result']
    assert result.get('roster') if scan else result.get('ok'), name
    return result


def scan_evidence(city):
    names = []
    for path in sorted(CAPTURE_Q.glob(city + '_scan*-result.json')):
        data = load(path)
        if data['httpStatus'] == 200 and data['result'].get('roster'):
            name = path.name.removesuffix('-result.json')
            receipt(name, scan=True)
            names.append(name)
    assert names, 'No successful fresh scan for ' + city
    return names


def episodes():
    m = load(CAPTURE_Q / 'marks.json')
    initial = load(CAPTURE_Q / 'initial-owned.json')
    final = load(CAPTURE_Q / 'final_bench.json')
    assert len(initial['creatures']) == 3 and len(final['creatures']) == 5
    assert {c['id'] for c in initial['creatures']} < {c['id'] for c in final['creatures']}

    def shot(key, offset, dur, line, face=False, y=190):
        start = round(m[key] + offset, 3)
        assert start >= 0
        # Each bench shot is held for five seconds after its screenshot marker.
        return (start, dur, 1, line, y, face)

    specs = [
        ('PB76', 'pigeon', 'pigeon-king', 1, 'royal-second-breakfast',
         'Pigeon King ordered a second breakfast.', 6.69,
         ['HIS MAJESTY IS HUNGRY.', 'SECOND MEAL. NO CEREMONY.', 'ANOTHER REAL FEED.', 'TWO OF FIVE. STILL ROYAL.']),
        ('PB77', 'egg', 'soft-egg', 1, 'soft-egg-round-two',
         'Soft Egg gets meal two. Still taking life softly.', 24,
         ['BREAKFAST FOR THE EGG.', 'SECOND MEAL. SAME VIBE.', 'ONE TAP. ONE MORE FEED.', 'TWO OF FIVE. TAKING IT EASY.']),
        ('PB78', 'moth', 'sprinkle-moth', 0, 'moth-first-meal',
         'Sprinkle Moth finally gets its first meal.', 18,
         ['SMALL WINGS. SNACK TIME.', 'FIRST MEAL FOR THE MOTH.', 'FIRST REAL FEED. DONE.', 'ONE OF FIVE. OFF WE GO.']),
    ]
    rows = []
    for eid, key, species_id, expected_before, slug, title, music, lines in specs:
        result = receipt(key + '_feed')
        before = next(c for c in initial['creatures'] if c['speciesId'] == species_id)
        after = next(c for c in final['creatures'] if c['id'] == before['id'])
        recorded_before = next(c for c in load(CAPTURE_Q / (key + '_bench_before.json'))['creatures'] if c['id'] == before['id'])
        recorded_after = next(c for c in load(CAPTURE_Q / (key + '_bench_after.json'))['creatures'] if c['id'] == before['id'])
        assert before['feedCount'] == expected_before
        assert result['creature']['id'] == before['id']
        assert result['creature']['feedCount'] == after['feedCount'] == before['feedCount'] + 1
        assert recorded_before['feedCount'] == before['feedCount'] and recorded_after['feedCount'] == after['feedCount']
        assert not result.get('justEvolved') and after['feedCount'] < 5
        name = result['species']['name']
        rows.append(dict(id=eid, slug=slug, name=name, title=title, duration=9.0, music_start=music,
                         evidence=[key + '_feed'], states=[key + '_bench_before', key + '_bench_after'],
                         note=f'Fresh gameplay recorded on 10 November 2026 in our continuing public filming profile. {name} receives a real feed: {before["feedCount"]}/5 to {after["feedCount"]}/5, after its actual cooldown. No evolution is shown or claimed.',
                         shots=[shot(key + '_bench_before', .1, 1.4, lines[0], face=True),
                                shot(key + '_feed_click', -.8, 1.6, lines[1]),
                                shot(key + '_feed_result', .15, 2.5, lines[2]),
                                shot(key + '_bench_after', .1, 3.5, lines[3])]))

    grant = receipt('house_claim')
    amount = grant['grantedMilli']
    assert grant['kind'] == 'house' and amount > 0
    rows.append(dict(id='PB79', slug='house-pips-next-stop', name='Daily house grant',
                     title=f'The house added {amount} game pips. Next stop: the map.', duration=9.0, music_start=13,
                     evidence=['house_claim'], states=['moth_bench_after', 'house_bench'],
                     note=f'The normal public daily house-grant button added {amount} in-game pips on 10 November 2026. The successful response and recorded bench balance support this grant. Pips are game credits, not money.',
                     shots=[shot('house_bench', .1, 1.4, 'THE MAP CAN WAIT ONE TAP.', face=True),
                            shot('house_claim_click', -1.3, 1.6, f'ADD {amount} GAME PIPS.'),
                            shot('house_claim_result', .1, 2.5, 'DAILY GRANT. CLAIMED.'),
                            shot('house_bench', .1, 3.5, "NOW LET'S FIND COMPANY.")]))

    for eid, city, label, ordinal, music, lines in [
        ('PB80', 'kyoto', 'Kyoto', 4, 10,
         ['KYOTO HAD COMPANY.', 'NEW PIN: KYOTO.', 'A NEW FACE ON THE MAP.', 'CAUGHT. JOIN THE BENCH.']),
        ('PB81', 'capetown', 'Cape Town', 5, 38.7,
         ['A FIFTH LITTLE FRIEND.', 'PIN: CAPE TOWN.', 'LOOK WHO THE SCAN FOUND.', 'CAUGHT. FIVE ON THE BENCH.']),
    ]:
        caught = receipt(city + '_catch')
        scans = scan_evidence(city)
        assert not caught.get('already')
        creature = caught['creature']
        assert creature['id'] not in {c['id'] for c in initial['creatures']}
        assert creature['id'] in {c['id'] for c in final['creatures']}
        name = caught['species']['name']
        assert len(load(CAPTURE_Q / (city + '_bench.json'))['creatures']) == ordinal
        last = 'final_bench' if city == 'capetown' else city + '_bench'
        title = f'Kyoto scan: {name} is coming home.' if city == 'kyoto' else f'Cape Town scan: {name} becomes pet number five.'
        rows.append(dict(id=eid, slug=city + '-new-friend', name=name, title=title, duration=10.0, music_start=music,
                         evidence=scans + [city + '_catch'], states=[city + '_bench', last],
                         note=f'A real public map scan at typed {label} coordinates and a successful catch of {name}, recorded on 10 November 2026. This becomes creature {ordinal} in our continuing filming profile. The scene shows remote map gameplay; it does not claim physical travel. Scan outcomes are examples.',
                         shots=[shot(city + '_bench', .1, 1.4, lines[0], face=True),
                                shot(city + '_coordinates', .1, 1.5, lines[1]),
                                shot(city + '_candidate', .1, 1.6, lines[2]),
                                shot(city + '_catch_click', -.7, 1.8, lines[3]),
                                shot(last, .1, 3.7, name.upper())]))
    return rows


def build(ep):
    raw = R / 'capture/raw-vertical.mp4'
    clips = []
    assert abs(sum(s[1] for s in ep['shots']) - ep['duration']) < .001
    for n, (start, dur, speed, line, y, face) in enumerate(ep['shots']):
        card = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((35, y, 1045, y + 140), radius=24, fill=(10, 18, 24, 242))
        b.label(card, line, y + 39, b.CREAM, 55)
        d.rounded_rectangle((50, 1745, 1030, 1800), radius=9, fill=(6, 10, 12, 230))
        b.label(card, 'REAL PLAY · 10 NOV 2026 · WAITING SHORTENED', 1755, b.CREAM, 25)
        if n == len(ep['shots']) - 1:
            d.rounded_rectangle((65, 1620, 1015, 1690), radius=12, fill=(6, 10, 12, 230))
            b.label(card, 'GET YOUR PET · LINK IN PROFILE', 1634, b.LIME, 34)
        png = W / f'{ep["id"]}-{n}.png'
        card.save(png)
        clip = W / f'{ep["id"]}-{n}.mp4'
        crop = 'crop=900:650:90:400,scale=1080:780,pad=1080:1920:0:550:color=0x060a0c,' if face else ''
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
               CAPTURE_Q / 'final_bench.json', CAPTURE_Q / 'marks.json', CAPTURE_Q / 'automation-classification.json',
               CAPTURE_Q / 'session-resumed.json']
    sources += [CAPTURE_Q / (name + '-result.json') for name in ep['evidence']]
    sources += [CAPTURE_Q / (name + '.json') for name in ep['states']]
    sources += [CAPTURE_Q / (city + '-choice.json') for city in ['kyoto', 'capetown'] if any(name.startswith(city + '_') for name in ep['evidence'])]
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
    assert summary['completed'] and summary['freshSession'] and summary['resumedOwnFilmingProfile'] and not summary.get('newProfileCreated', False)
    for ep in episodes():
        if len(sys.argv) == 1 or ep['id'] in sys.argv[1:]:
            build(ep)
