"""Build six Shorts from this series' newly rendered PingBlip character footage."""
from pathlib import Path
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import json
import math
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parents[2] / 'PromoMaterials/blip/youtube-season-something-pinged'
BATCH = 'v23-bench-matchups'
WORK = ROOT / 'work'
FINAL = ROOT / 'final'
MODELS = ROOT.parents[1] / 'pingblip/memeforge/public/models'
spec = spec_from_file_location('style', PACK / 'v14-action-first/source/build_batch.py')
style = module_from_spec(spec)
spec.loader.exec_module(style)

# Alternate which format gets the earlier slot during the three days.
EPISODES = [
    ('PB88', 'ride-home', 'choice', ['taxi-larva', 'rain-pigeon'],
     'You missed the last bus. Taxi Larva or Rain Pigeon?',
     ['YOU MISSED THE BUS.', 'PICK YOUR RIDE.'], '#ffd976', '#bacfea', 3),
    ('PB89', 'sewing-kit', 'reveal', ['button-spider'],
     'My sewing kit walked away.',
     ['MY BUTTONS MOVED.', 'MY SEWING KIT ESCAPED.'], '#392346', '#f2d7e8', 15),
    ('PB90', 'museum-snack', 'reveal', ['caramel-bust'],
     'The museum said no snacks. Meet Caramel Bust.',
     ['NO SNACKS IN THE MUSEUM.', 'THE STATUE IS CARAMEL.'], '#402519', '#f7d6a9', 23),
    ('PB91', 'candy-draft', 'choice', ['lollipop-golem', 'sour-worm'],
     'Pick your candy creature. Lollipop Golem or Sour Worm?',
     ['PICK YOUR CANDY.', 'SWEET OR SOUR?'], '#ffc9df', '#d9ef9b', 30),
    ('PB92', 'workbench', 'choice', ['tongs-golem', 'winged-bolt'],
     'Who gets the last spot at the workbench? Tongs Golem or Winged Bolt?',
     ['ONE SPOT AT THE BENCH.', 'TONGS OR BOLT?'], '#fed2ae', '#c5dbf7', 9),
    ('PB93', 'mirror-idol', 'reveal', ['mirror-idol'],
     'The mirror has a roommate. Meet Mirror Idol.',
     ['LOOK IN THE MIRROR.', 'THE MIRROR HAS A ROOMMATE.'], '#211a46', '#d9d4fa', 36),
]

INK = '#222032'
WHITE = '#fff4e0'
WIDTH, HEIGHT = 1080, 1920
FPS = 30
SECONDS = 8
FADE_EDGE = Image.new('L', (1, 1030))
FADE_EDGE.putdata([round(255 * min(1, y / 46, (1029 - y) / 115)) for y in range(1030)])
OPENING_MASK = FADE_EDGE.resize((1080, 1030))

def title(image, label, y, size, color=INK):
    style.b.centered(ImageDraw.Draw(image), label, y, size, color, max_w=910)

def small(image, label, y, size=37, color=INK):
    style.b.centered(ImageDraw.Draw(image), label, y, size, color, 'plex', max_w=880)

def name(slug):
    return slug.replace('-', ' ').title()

@lru_cache(maxsize=192)
def figure(slug, index):
    im = Image.open(WORK / slug / f'{index:03d}.png').convert('RGBA')
    return im.crop(im.getbbox())

def place(canvas, slug, n, x, y, w, h, *, zoom=1, focus=.45):
    a = figure(slug, (n // 5) % 24)
    scale = zoom * min(w / a.width, h / a.height)
    a = a.resize((round(a.width*scale), round(a.height*scale)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(a, (round(x+w/2-a.width/2),round(y+h/2-a.height*focus)))

def reveal(ep,n):
    _,_,_,slugs,_,words,dark,pastel,_ = ep
    slug = slugs[0]
    t = n / FPS
    opening = t < 1.45
    base = Image.new('RGBA',(WIDTH,HEIGHT), dark if opening else pastel)
    color = WHITE if opening else INK
    stage = Image.new('RGBA',(1080,1030))
    draw = ImageDraw.Draw(stage)
    if opening:
        draw.ellipse((12,45,1068,1010), fill='#ffffff0b')
        place(stage,slug,n,0,25,1080,980,zoom=1.6+.12*t,focus=.39)
        stage.putalpha(ImageChops.multiply(stage.getchannel('A'), OPENING_MASK))
        base.alpha_composite(stage,(0,450))
    else:
        draw.ellipse((100,40,920,925), fill='#ffffff61')
        draw.ellipse((170,815,855,865), fill='#6c396330')
        ext = 1 + .08 * math.exp(-(t-1.45)*4)
        place(stage,slug,n,55,25,890,875,zoom=ext,focus=.52)
        base.alpha_composite(stage,(-29,450))
    small(base,'PINGBLIP',200,30,color)
    title(base,words[0 if opening else 1],315,93,color)
    if not opening:
        small(base,name(slug).upper(),1415,43)
    if t >= 6.8:
        small(base,'PLAY FREE · LINK IN PROFILE',1565,34)
    return base

def choice(ep,n):
    _,_,_,slugs,_,words,left,right,_ = ep
    t = n / FPS
    base = Image.new('RGBA',(WIDTH,HEIGHT),'#faf4ed')
    title(base,words[0] if t<2.3 else words[1],310,94)
    small(base,'PINGBLIP',200,30)
    for j,(slug,bg) in enumerate(zip(slugs,(left,right))):
        x = 55 + 440*j
        card = Image.new('RGBA',(422,785))
        c = ImageDraw.Draw(card)
        c.rounded_rectangle((0,0,421,784),radius=43,fill=bg)
        c.ellipse((32,100,390,636),fill='#ffffff70')
        beat = t - (2.3 + 1.4 * j)
        pulse = 1 + .1 * math.sin(math.pi * beat / 1.4) if 0 <= beat <= 1.4 else 1
        place(card,slug,n+23*j,14,90,394,580,zoom=pulse,focus=.52)
        c.text((211,717),f'{j+1}  {name(slug).upper()}',font=style.b.font(32,'plex'),
               anchor='mm',fill=INK)
        base.alpha_composite(card,(x,514))
    title(base,'1 OR 2?',1400,77)
    if t >= 6.8:
        small(base,'PLAY FREE · LINK IN PROFILE',1565,34)
    return base

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build(ep):
    eid, slug, kind, models, heading, _, _, _, cut = ep
    silent = WORK / f'{eid}-silent.mp4'
    final = FINAL / f'{eid}-{slug}.mp4'
    cmd = ['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
           '-s',f'{WIDTH}x{HEIGHT}','-r',str(FPS),'-i','-','-an','-c:v','libx264',
           '-preset','veryfast','-crf','18','-threads','3','-pix_fmt','yuv420p',str(silent)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as encoder:
        for n in range(SECONDS * FPS):
            im = (reveal if kind=='reveal' else choice)(ep,n)
            encoder.stdin.write(im.convert('RGB').tobytes())
        encoder.stdin.close()
        assert encoder.wait()==0
    route = style.mux({'music_start':cut},silent,SECONDS,final)
    names = ' and '.join(name(s) for s in models)
    description = (f'{heading}\n\n{names} in a short animation made with PingBlip game models. '
                   'The characters shown are examples. Play free via the game link on @PingBlip.\n\n'
                   'Music: PingBlip original, AI-generated.\n#PingBlip #BrowserGame #CreatureCollector')
    final.with_suffix('.txt').write_text(heading+'\n\n'+description+'\n')
    print(eid,final.name,flush=True)
    return {'id':eid,'file':f'{BATCH}/final/{final.name}','kind':kind,'name':names,
            'title':heading,'description':description,'sha256':sha(final),'duration':SECONDS,
            'musicEdit':route,'visualApproved':False,
            'sources':[{'file':str(MODELS / f'{s}.glb'),'sha256':sha(MODELS / f'{s}.glb')} for s in models]}

if __name__=='__main__':
    FINAL.mkdir(exist_ok=True)
    mp = FINAL / 'manifest.json'
    rows = {r['id']:r for r in json.loads(mp.read_text())} if mp.exists() else {}
    for ep in EPISODES:
        if len(sys.argv)==1 or ep[0] in sys.argv[1:]:
            rows[ep[0]]=build(ep)
    mp.write_text(json.dumps([rows[e[0]] for e in EPISODES if e[0] in rows],indent=2)+'\n')
