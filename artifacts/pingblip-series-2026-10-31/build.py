"""Six new edits from verified footage and existing approved character assets."""
from pathlib import Path
import hashlib, importlib.util, json, math, subprocess, sys
from PIL import Image, ImageDraw
from snapshot import A, P

R = P/'v16-new-friends'
W, F, Q = A/'work', R/'final', A/'qa'
spec = importlib.util.spec_from_file_location('style', P/'v14-action-first/source/build_batch.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
b.W = W
EPISODES = [
    dict(id='PB47',slug='unexpected-rat',kind='gameplay',name='Rat Oracle',duration=7.4,music_start=6.69,
         title='I asked for a pet. The universe sent this rat.',capture='v10-weird-one/capture-session',
         note='A new edit of previously recorded real Rat Oracle hatching. Waiting shortened. This was one real outcome, not a guaranteed hatch.',
         shots=[(26,1.1,1,'I ASKED FOR A PET.',190),(7.3,1.7,1.8,'THE UNIVERSE SAID...',1325),(10.8,2.3,1,'RAT. WITH A HALO.',1325),(27.5,2.3,1,'OKAY. I LOVE HIM.',190)]),
    dict(id='PB48',slug='lollipop-roommate',kind='gameplay',name='Lollipop Golem',duration=7.6,music_start=18,
         title='Scanned Los Angeles. Found a lollipop roommate.',capture='v10-weird-one/capture-catch',
         note='A new edit of the previously recorded successful Los Angeles scan and catch of Lollipop Golem. Waiting shortened. This location and creature are examples, not a guaranteed catch.',
         shots=[(48.3,1.0,1,'NEW ROOMMATE FOUND.',190),(23.4,1.3,1.3,'I SCANNED LOS ANGELES.',190),(33.9,2.0,1.2,'CAUGHT. COMING HOME.',190),(48.7,3.3,1,'HE SEEMS PRETTY SWEET.',190)]),
    dict(id='PB49',slug='egg-calendar',kind='comedy',name='Soft Egg',duration=7.4,music_start=24,
         title='My calendar is full. My pet has zero plans.',
         note='A character joke with the approved Soft Egg game model. Promotional animation, not gameplay.'),
    dict(id='PB50',slug='tiny-haunting',kind='reveal',name='Gummy Wraith',duration=7.4,music_start=10,
         title='Thought my room was haunted. It just wanted company.',
         note='A friendly reveal with the approved Gummy Wraith game model. Promotional animation, not gameplay.'),
    dict(id='PB51',slug='last-brain-cell',kind='choice',name='Bruised Banana / Angry Dumpling',duration=7.6,music_start=13,
         title='Your last two brain cells: banana or dumpling?',
         note='A playful mood choice using the approved Bruised Banana and Angry Dumpling game models. Promotional animation, not gameplay.'),
    dict(id='CL21',slug='sprinkle-moth',kind='library',name='Sprinkle Moth',
         title='Sprinkle Moth — tiny wings, serious sprinkles.',
         note='Previously unpublished supplied Sprinkle Moth creature clip with its existing close-up opening and revised closing captions. Promotional creature animation, not gameplay.'),
]

def save(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def gameplay(ep,out):
    folder=P/ep['capture']; raw=folder/'raw-vertical.mp4'
    evidence=folder/('hatch-result.json' if ep['id']=='PB47' else 'catch-result.json')
    result=json.loads(evidence.read_text())
    assert result['httpStatus']==200 and result['result']['ok']
    assert result['result']['creature']['speciesId']==('rat-oracle' if ep['id']=='PB47' else 'lollipop-golem')
    clips=[]
    for n,(start,dur,speed,line,y) in enumerate(ep['shots']):
        card=Image.new('RGBA',(1080,1920),(0,0,0,0));d=ImageDraw.Draw(card)
        d.rounded_rectangle((35,y,1045,y+130),radius=24,fill=(10,18,24,242))
        b.label(card,line,y+37,b.CREAM,47)
        b.label(card,'REAL GAMEPLAY · WAITING SHORTENED',1750,b.CREAM,26)
        if n==len(ep['shots'])-1:
            b.label(card,'YOUR LITTLE WEIRDO · LINK IN PROFILE',1640,b.LIME,32)
        png=W/f'{ep["id"]}-{n}.png'; card.save(png)
        clip=W/f'{ep["id"]}-{n}.mp4'
        b.run(['ffmpeg','-v','error','-y','-ss',start,'-i',raw,'-loop','1','-i',png,
               '-filter_complex_threads','1','-filter_complex',f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30,tpad=stop_mode=clone:stop_duration=2[v];[v][1:v]overlay=0:0,format=yuv420p[o]',
               '-map','[o]','-an','-t',dur,'-c:v','libx264','-crf','18','-preset','veryfast','-threads','2',clip])
        clips.append(clip)
    concat=W/f'{ep["id"]}.ffconcat';concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{x}'\n" for x in clips))
    silent=W/f'{ep["id"]}-silent.mp4'
    b.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',silent])
    return b.mux(ep,silent,ep['duration'],out),[raw,evidence]

def character_frame(ep,n):
    t=n/30;idx=1+int(t*12)%48
    if ep['kind']=='comedy':
        im=Image.new('RGBA',(1080,1920),'#fff0d2')
        before=t<2.5
        b.text(im,['MY CALENDAR:','FULL.'] if before else ['HIS CALENDAR:','ABSOLUTELY EMPTY.'],y=245,size=87,color=b.INK)
        box=(-300,560,1640,1900) if before else (65,540,910,1010)
        b.place(im,'soft-egg',idx,box)
        if not before:b.label(im,'SOFT EGG · LIFE COACH',1550,b.INK,33)
        color=b.INK
    elif ep['kind']=='reveal':
        dark=t<2.2
        im=Image.new('RGBA',(1080,1920),'#181b31' if dark else '#d9f2ed')
        color=b.CREAM if dark else b.INK
        b.text(im,['I HEARD','A GHOST.'] if dark else ['IT JUST WANTED','COMPANY.'],y=260,size=91,color=color)
        # The opening is an enlarged face; the second shot reveals the real model.
        b.place(im,'gummy-wraith',idx,(-300,540,1640,1900) if dark else (130,600,780,880))
        if not dark:b.label(im,'GUMMY WRAITH · TINY HAUNTING',1550,color,30)
    else:
        im=Image.new('RGBA',(1080,1920),'#f1e8f3');color=b.INK
        b.text(im,['MY LAST TWO','BRAIN CELLS.'] if t<2.9 else ['WHICH ONE','ARE YOU TODAY?'],y=250,size=94,color=color)
        d=ImageDraw.Draw(im)
        d.rounded_rectangle((40,565,510,1410),radius=38,fill='#fae4a9')
        d.rounded_rectangle((530,565,1000,1410),radius=38,fill='#f2b6a5')
        bob=12*math.sin(t*2.5)
        b.place(im,'bruised-banana',idx,(80,600+bob,380,710))
        b.place(im,'angry-dumpling',1+(idx+14)%48,(550,690-bob,430,570))
        d.text((275,1320),'1 · BANANA',font=b.b.font(36,'plex'),fill=color,anchor='mt')
        d.text((765,1320),'2 · DUMPLING',font=b.b.font(36,'plex'),fill=color,anchor='mt')
        b.label(im,'1 OR 2?',1510,color,66)
    b.label(im,'PINGBLIP',185,color,27)
    if t>ep['duration']-1.3:
        b.label(im,'YOUR LITTLE WEIRDO · LINK IN PROFILE',1660,color,30)
    return im.convert('RGB')

def character(ep,out):
    silent=W/f'{ep["id"]}-silent.mp4'
    proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r','30','-i','-','-an','-c:v','libx264','-crf','18','-preset','veryfast','-threads','2','-pix_fmt','yuv420p',str(silent)],stdin=subprocess.PIPE)
    for n in range(round(ep['duration']*30)):
        proc.stdin.write(character_frame(ep,n).tobytes())
    proc.stdin.close();assert proc.wait()==0
    slugs={'comedy':['soft-egg'],'reveal':['gummy-wraith'],'choice':['bruised-banana','angry-dumpling']}[ep['kind']]
    return b.mux(ep,silent,ep['duration'],out),[P/'v13-ten-redesigns/source/models'/f'{s}.glb' for s in slugs]

def build(ep):
    out=F/f'{ep["id"]}-{ep["slug"]}.mp4'
    if ep['kind']=='library':
        source=P.parent/'closeup/clips'/f'{ep["slug"]}.mp4'
        card=Image.new('RGBA',(1080,1920),(0,0,0,0));d=ImageDraw.Draw(card)
        d.rectangle((0,1610,1080,1920),fill='#14090c')
        b.label(card,'TINY WINGS. SERIOUS SPRINKLES.',1650,b.CREAM,31)
        b.label(card,'PLAY · LINK IN PROFILE',1760,b.LIME,31)
        png=W/'CL21-footer.png';card.save(png)
        b.run(['ffmpeg','-v','error','-y','-i',source,'-loop','1','-i',png,'-filter_complex_threads','1',
               '-filter_complex','[0:v][1:v]overlay=0:0:shortest=1,format=yuv420p[v]',
               '-map','[v]','-map','0:a','-c:v','libx264','-crf','18','-preset','veryfast','-threads','2','-c:a','copy','-movflags','+faststart',out])
        ep['duration']=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(out)]))['format']['duration'])
        music=None;sources=[source]
    elif ep['kind']=='gameplay':
        music,sources=gameplay(ep,out)
    else:
        music,sources=character(ep,out)
    desc=ep['note']+'\n\nPlay free: open @PingBlip and tap the game link in our profile.\nhttps://pingblip.com/\nThe creatures shown are examples; your first creature is a surprise.\n\nMusic: PingBlip original, AI-generated.\n#PingBlip #BrowserGame #CreatureCollector'
    if ep['kind']=='gameplay':desc+='\nGame pips are in-game credits, not money.'
    row={**ep,'file':str(out.relative_to(P)),'description':desc,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'musicEdit':music,
         'sources':[{'file':str(s),'sha256':hashlib.sha256(s.read_bytes()).hexdigest()} for s in sources],'visualApproved':False}
    path=F/'manifest.json';rows=json.loads(path.read_text()) if path.exists() else []
    rows=[x for x in rows if x['id']!=ep['id']]+[row];save(path,rows)
    out.with_suffix('.txt').write_text(ep['title']+'\n\n'+desc+'\n')
    b.run(['ffmpeg','-v','error','-y','-ss','0.5','-i',out,'-frames:v','1',out.with_suffix('.jpg')])
    print('BUILT',ep['id'],ep['kind'],ep['duration'],flush=True)

if __name__=='__main__':
    for path in [W,F,Q]:path.mkdir(parents=True,exist_ok=True)
    for ep in EPISODES:
        if len(sys.argv)==1 or ep['id'] in sys.argv[1:]:build(ep)
