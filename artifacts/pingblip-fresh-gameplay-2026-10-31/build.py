"""Build six Shorts exclusively from this batch's newly recorded game session."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, sys
from PIL import Image,ImageDraw
from capture import A,P,R,Q as CAPTURE_Q

W=A/'work';F=R/'final';Q=A/'qa'
spec=importlib.util.spec_from_file_location('style',P/'v14-action-first/source/build_batch.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def load(path):return json.loads(path.read_text())
def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def receipt(name):
    data=load(CAPTURE_Q/(name+'-result.json'))
    assert data['httpStatus']==200 and data['result'].get('ok')
    assert data['recordedAt']>=1793476200,'Action predates this fresh recording task'
    return data['result']

def episodes():
    m=load(CAPTURE_Q/'marks.json')
    hatch=receipt('hatch');feed=receipt('starter_feed');grant=receipt('house_claim')
    a=receipt('amsterdam_catch');af=receipt('caught_feed');t=receipt('tokyo_catch')
    assert not hatch['already'] and not a['already'] and not t['already']
    assert feed['creature']['feedCount']==1 and af['creature']['feedCount']==1
    assert af['creature']['id']==a['creature']['id']
    starter=hatch['species']['name'];caught=a['species']['name'];tokyo=t['species']['name']
    def shot(key,offset,dur,speed,line,y=190,face=False):return (round(m[key]+offset,3),dur,speed,line,y,face)
    return [
        dict(id='PB52',slug='fresh-hatch',name=starter,title=f'I pressed hatch. {starter} moved in.',duration=8.0,music_start=6.69,
             evidence=['hatch'],note=f'Fresh game session recorded 31 October 2026. A real first hatch produced {starter}; this outcome is an example, not a guaranteed hatch.',
             shots=[shot('starter_bench',0,1.0,1,'THIS GUY JUST MOVED IN.',face=True),shot('hatch_click',-.2,1.7,1.4,'ONE TAP. A NEW PET.',1325),shot('hatch_result',.5,2.2,1,starter.upper(),1325),shot('starter_bench',1.3,3.1,1,'HE BROUGHT HIS OWN LID.')]),
        dict(id='PB53',slug='fresh-raccoon-feed',name=starter,title=f'First real feed for my {starter}.',duration=8.5,music_start=18,
             evidence=['starter_feed'],note=f'Fresh footage of the first successful feed of {starter}, recorded 31 October 2026. Real 0/5 to 1/5 progression.',
             shots=[shot('starter_bench',.5,1.1,1,'NEW PET. FIRST SNACK.',face=True),shot('starter_feed_click',-.8,1.3,1,'ONE REAL FEED.'),shot('starter_feed_result',-.2,2.5,1,'SNACK DELIVERED.'),shot('starter_fed_bench',-3.5,3.6,1,'ONE OF FIVE. WE STARTED.')]),
        dict(id='PB54',slug='fresh-house-pips',name=starter,title='250 free game pips. My raccoon approves.',duration=8.0,music_start=24,
             evidence=['house_claim'],note='Fresh recording of the daily 250-pip house grant, claimed through the normal public game button on 31 October 2026. Pips are game credits, not money.',
             shots=[shot('house_bench',0,1.0,1,'MY PET HAS A BUDGET.',face=True),shot('house_claim_click',-1.4,1.5,1,'250 FREE GAME PIPS.'),shot('house_claim_result',-.3,2.5,1,'CLAIMED. ON THE HOUSE.'),shot('house_bench',1,3.0,1,'LUNCH IS SORTED.')]),
        dict(id='PB55',slug='fresh-amsterdam-catch',name=caught,title=f'Scanned Amsterdam. Caught {caught}.',duration=9.0,music_start=13,
             evidence=['amsterdam_catch'],note=f'Fresh Amsterdam weather scan and successful catch of {caught}, recorded 31 October 2026. Coordinates were typed into the game; this is remote map gameplay, not a claim of physical travel.',
             shots=[shot('amsterdam_bench',0,1.0,1,'AMSTERDAM SENT A FRIEND.',face=True),shot('amsterdam_coordinates',0,1.4,1,'PIN: AMSTERDAM.'),shot('amsterdam_scan_click',-.2,1.3,1.4,'SCANNING THE MAP.'),shot('amsterdam_catch_result',-.7,2.0,1,'CAUGHT. COMING HOME.'),shot('amsterdam_bench',1.2,3.3,1,caught.upper())]),
        dict(id='PB56',slug='fresh-caught-feed',name=caught,title=f'Caught {caught}. First stop: snack time.',duration=8.4,music_start=10,
             evidence=['caught_feed'],note=f'Fresh first feed of the newly caught {caught}, recorded 31 October 2026. A successful action and the persisted 1/5 result are shown.',
             shots=[shot('amsterdam_bench',.5,1.1,1,'CAUGHT. ALREADY HUNGRY.',face=True),shot('caught_feed_click',-.7,1.3,1,'WELCOME-HOME SNACK.'),shot('caught_feed_result',-.2,2.4,1,'ONE TAP. FIRST FEED.'),shot('caught_fed_bench',.4,3.6,1,'ONE OF FIVE. OUR LITTLE GUY.')]),
        dict(id='PB57',slug='fresh-tokyo-catch',name=tokyo,title=f'Tokyo scan: {tokyo} joined my bench.',duration=9.0,music_start=38.7,
             evidence=['tokyo_catch'],note=f'Fresh Tokyo weather scan and successful catch of {tokyo}, recorded 31 October 2026. The same new session now owns three creatures. Coordinates were typed; this does not claim physical travel.',
             shots=[shot('tokyo_bench',0,1.0,1,'TOKYO FOUND OUR THIRD.',face=True),shot('tokyo_coordinates',0,1.3,1,'NEXT PIN: TOKYO.'),shot('tokyo_scan_click',-.2,1.4,1.4,'A NEW SIGNAL.'),shot('tokyo_catch_click',-.3,2.0,1,'ANOTHER LITTLE FRIEND.'),shot('final_bench',.1,3.3,1,tokyo.upper())]),
    ]

def build(ep):
    raw=R/'capture/raw-vertical.mp4';clips=[]
    for n,(start,dur,speed,line,y,face) in enumerate(ep['shots']):
        card=Image.new('RGBA',(1080,1920),(0,0,0,0));d=ImageDraw.Draw(card)
        d.rounded_rectangle((35,y,1045,y+140),radius=24,fill=(10,18,24,242))
        b.label(card,line,y+39,b.CREAM,55)
        d.rounded_rectangle((50,1745,1030,1800),radius=9,fill=(6,10,12,230))
        b.label(card,'FRESH GAMEPLAY · 31 OCT 2026 · WAITING SHORTENED',1755,b.CREAM,24)
        if n==len(ep['shots'])-1:
            d.rounded_rectangle((65,1620,1015,1690),radius=12,fill=(6,10,12,230))
            b.label(card,'GET YOUR PET · LINK IN PROFILE',1634,b.LIME,34)
        png=W/f'{ep["id"]}-{n}.png';card.save(png)
        clip=W/f'{ep["id"]}-{n}.mp4'
        crop='crop=900:650:90:400,scale=1080:780,pad=1080:1920:0:550:color=0x060a0c,' if face else ''
        b.run(['ffmpeg','-v','error','-y','-ss',start,'-i',raw,'-loop','1','-i',png,'-filter_complex_threads','1',
               '-filter_complex',f'[0:v]setpts=(PTS-STARTPTS)/{speed},{crop}fps=30,tpad=stop_mode=clone:stop_duration=2[v];[v][1:v]overlay=0:0,format=yuv420p[o]',
               '-map','[o]','-an','-t',dur,'-c:v','libx264','-crf','18','-preset','veryfast','-threads','2',clip])
        clips.append(clip)
    concat=W/f'{ep["id"]}.ffconcat';concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{x}'\n" for x in clips))
    silent=W/f'{ep["id"]}-silent.mp4';b.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',silent])
    out=F/f'{ep["id"]}-{ep["slug"]}.mp4';music=b.mux(ep,silent,ep['duration'],out)
    evidence=[CAPTURE_Q/(name+'-result.json') for name in ep['evidence']]
    sources=[raw]+evidence
    desc=ep['note']+'\nWaiting shortened; all game footage comes from this fresh session.\n\nGet your pet free through the game link on @PingBlip.\nhttps://pingblip.com/\nYour first creature is a surprise; the creatures and map results shown are examples.\nGame pips are in-game credits, not money.\n\nMusic: PingBlip original, AI-generated.\n#PingBlip #BrowserGame #CreatureCollector'
    row={**ep,'kind':'gameplay','freshGameplay':True,'recordedAtUtc':load(CAPTURE_Q/'capture-summary.json')['recordedAtUtc'],'file':str(out.relative_to(P)),
         'description':desc,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'musicEdit':music,
         'sources':[{'file':str(s),'sha256':hashlib.sha256(s.read_bytes()).hexdigest()} for s in sources],'visualApproved':False}
    path=F/'manifest.json';rows=load(path) if path.exists() else [];rows=[r for r in rows if r['id']!=ep['id']]+[row];save(path,rows)
    out.with_suffix('.txt').write_text(ep['title']+'\n\n'+desc+'\n')
    b.run(['ffmpeg','-v','error','-y','-ss','0.5','-i',out,'-frames:v','1',out.with_suffix('.jpg')])
    print('BUILT',ep['id'],ep['name'],ep['duration'],flush=True)

if __name__=='__main__':
    for path in [W,F,Q]:path.mkdir(parents=True,exist_ok=True)
    summary=load(CAPTURE_Q/'capture-summary.json');assert summary['completed'] and summary['freshSession']
    for ep in episodes():
        if len(sys.argv)==1 or ep['id'] in sys.argv[1:]:build(ep)
