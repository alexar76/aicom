"""Fully decode PB76–PB81, validate evidence hashes, measure audio and render QA sheets.

Visual approval deliberately remains false until a human/model inspects the
rendered sheets and any detailed frames required by that inspection.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from capture import A, P, R, Q as CAPTURE_Q

Q = A / 'qa'


def load(path):
    return json.loads(path.read_text())


def main():
    Q.mkdir(parents=True, exist_ok=True)
    manifest = load(R / 'final/manifest.json')
    assert len(manifest) == 6 and {ep['id'] for ep in manifest} == {f'PB{i}' for i in range(76, 82)}
    summary = load(CAPTURE_Q / 'capture-summary.json')
    assert summary['completed'] and summary['freshSession'] and summary['resumedOwnFilmingProfile'] and not summary.get('newProfileCreated', False)
    raw = R / 'capture/raw-vertical.mp4'
    raw_probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(raw)]))
    raw_video = next(s for s in raw_probe['streams'] if s['codec_type'] == 'video')
    raw_duration = float(raw_video['duration'])
    report, source_hashes = [], {}
    overview = Image.new('RGB', (270 * 6, 520 * len(manifest)), '#27292b')
    for row_index, ep in enumerate(sorted(manifest, key=lambda e: e['id'])):
        f = P / ep['file']
        p = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(f)]))
        v = next(s for s in p['streams'] if s['codec_type'] == 'video')
        a = next(s for s in p['streams'] if s['codec_type'] == 'audio')
        dur = float(v['duration'])
        assert (v['width'], v['height'], v['r_frame_rate']) == (1080, 1920, '30/1'), f
        assert v['codec_name'] == 'h264' and v.get('pix_fmt') in ['yuv420p', 'yuvj420p'] and a['codec_name'] == 'aac'
        assert 8 <= dur <= 12
        assert abs(dur - float(a['duration'])) < .08
        assert abs(dur - ep['duration']) < .08
        assert abs(sum(shot[1] for shot in ep['shots']) - ep['duration']) < .001
        for start, duration, speed, *_ in ep['shots']:
            assert start >= 0 and duration > 0 and speed > 0
            assert start + duration * speed <= raw_duration + (1 / 30), ('Shot exceeds recorded source', ep['id'], start, duration, raw_duration)
        assert hashlib.sha256(f.read_bytes()).hexdigest() == ep['sha256']
        for source in ep['sources']:
            path = source['file']
            if path not in source_hashes:
                source_hashes[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            assert source_hashes[path] == source['sha256'], ('Source changed after build', path)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(f), '-f', 'null', '-'], check=True)
        measure = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(f), '-af',
                                  'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
                                 capture_output=True, text=True, check=True)
        loud = json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}', measure.stderr).group())
        assert abs(float(loud['input_i']) + 14) < 1.1, (f, loud)
        assert float(loud['input_tp']) < -.8, (f, loud)
        times = [0, .8, dur * .32, dur * .52, dur * .77, dur - .35]
        sheet = Image.new('RGB', (270 * 6, 520), '#27292b')
        detail = Image.new('RGB', (540 * 6, 1000), '#27292b')
        for n, t in enumerate(times):
            png = Q / f'{ep["id"]}-{n}.jpg'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', str(f), '-frames:v', '1',
                            '-vf', 'scale=540:960', str(png)], check=True)
            im = Image.open(png)
            detail.paste(im, (n * 540, 0))
            ImageDraw.Draw(detail).text((n * 540 + 8, 974), f'{ep["id"]}  {t:.2f}s', fill='white')
            sheet.paste(im.resize((270, 480), Image.Resampling.LANCZOS), (n * 270, 0))
            ImageDraw.Draw(sheet).text((n * 270 + 6, 490), f'{ep["id"]}  {t:.2f}s', fill='white')
        sheet.save(Q / f'{ep["id"]}-contact.jpg')
        detail.save(Q / f'{ep["id"]}-detail.jpg')
        overview.paste(sheet, (0, row_index * 520))
        report.append({'id': ep['id'], 'file': ep['file'], 'duration': dur, 'sha256': ep['sha256'],
                       'width': v['width'], 'height': v['height'], 'fps': v['r_frame_rate'],
                       'pixelFormat': v['pix_fmt'], 'colorRange': v.get('color_range'),
                       'audioDuration': float(a['duration']), 'loudness': loud, 'decodePassed': True,
                       'sourceHashesVerified': True, 'sourceCutsBounded': True, 'rawDuration': raw_duration, 'visualApproved': False})
        print(ep['id'], round(dur, 2), loud['input_i'], 'LUFS', loud['input_tp'], 'dBTP', flush=True)
    overview.save(Q / 'all-contact.jpg')
    (Q / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Media checks passed; visual review remains required.', flush=True)


if __name__ == '__main__':
    main()
