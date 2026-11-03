"""Decode the complete batch, measure audio, and make visual review sheets."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

from snapshot import A, P
R=P/'v16-new-friends'
Q=A/'qa'
manifest=json.loads((R/'final/manifest.json').read_text())
report=[]
overview=Image.new('RGB',(270*6,520*len(manifest)),'#27292b')
for row_index,ep in enumerate(manifest):
    f=P/ep['file']
    p=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]))
    v=next(s for s in p['streams'] if s['codec_type']=='video')
    a=next(s for s in p['streams'] if s['codec_type']=='audio')
    dur=float(v['duration'])
    assert (v['width'],v['height'],v['r_frame_rate'])==(1080,1920,'30/1'),f
    assert v['codec_name']=='h264' and a['codec_name']=='aac'
    assert abs(dur-float(a['duration']))<.08
    assert abs(dur-ep['duration'])<.08
    assert hashlib.sha256(f.read_bytes()).hexdigest()==ep['sha256']
    subprocess.run(['ffmpeg','-v','error','-i',str(f),'-f','null','-'],check=True)
    measure=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(f),'-af',
                            'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],
                           capture_output=True,text=True,check=True)
    loud=json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}',measure.stderr).group())
    if ep['kind']!='library':
        assert abs(float(loud['input_i'])+14)<1.1,(f,loud)
        assert float(loud['input_tp'])<-.8,(f,loud)
    else:
        assert -25<float(loud['input_i'])<-8,(f,loud)
        assert float(loud['input_tp'])<0,(f,loud)
    times=[.0,.8,dur*.32,dur*.52,dur*.77,dur-.35]
    sheet=Image.new('RGB',(270*6,520),'#27292b')
    for n,t in enumerate(times):
        png=Q/f'{ep["id"]}-{n}.jpg'
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(f),'-frames:v','1','-vf','scale=270:480',str(png)],check=True)
        sheet.paste(Image.open(png),(n*270,0))
        ImageDraw.Draw(sheet).text((n*270+6,490),f'{ep["id"]}  {t:.2f}s',fill='white')
    sheet.save(Q/f'{ep["id"]}-contact.jpg')
    overview.paste(sheet,(0,row_index*520))
    report.append({'id':ep['id'],'file':ep['file'],'duration':dur,'sha256':ep['sha256'],
                   'width':v['width'],'height':v['height'],'fps':v['r_frame_rate'],
                   'audioDuration':float(a['duration']),'loudness':loud,'decodePassed':True,
                   'visualApproved':False})
    print(ep['id'],round(dur,2),loud['input_i'],'LUFS',loud['input_tp'],'dBTP',flush=True)
overview.save(Q/'all-contact.jpg')
(Q/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
