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
    summary=load(CAPTURE_Q/'capture-summary.json')
    assert data['httpStatus']==200 and data['result'].get('ok')
    assert data['recordedAt']>=summary['recordingStartUnix'],'Action predates this recording'
    return data['result']

def episodes():
    m=load(CAPTURE_Q/'marks.json')
    r=receipt('raccoon_feed');d=receipt('donut_feed');banana=receipt('banana_feed');grant=receipt('house_claim')
    l=receipt('london_catch');n=receipt('newyork_catch')
    assert not l['already'] and not n['already'] and grant['grantedMilli']==250
    for key,result in [('raccoon',r),('donut',d),('banana',banana)]:
        before=load(CAPTURE_Q/(key+'-before.json'));after=load(CAPTURE_Q/(key+'-after.json'))
        assert result['creature']['feedCount']==before['feedCount']+1==after['feedCount']
    assert r['creature']['feedCount']==2 and d['creature']['feedCount']==2 and banana['creature']['feedCount']==1
    lc=load(CAPTURE_Q/'london-choice.json');nc=load(CAPTURE_Q/'newyork-choice.json')
    def shot(key,offset,dur,speed,line,y=190,face=False):return (round(m[key]+offset,3),dur,speed,line,y,face)
    rows=[]
    specs=[
      ('PB58','raccoon','raccoon-second-snack',r,'Back to my Dumpster Raccoon. Snack number two.',6.69,
       ['BACK TO MY LITTLE BOSS.','TIME FOR SNACK NUMBER TWO.','ONE REAL FEED.','TWO OF FIVE. GETTING THERE.']),
      ('PB59','donut','donut-second-snack',d,'My Glaze Donut had one request: more breakfast.',18,
       ['HE STILL WANTS BREAKFAST.','SECOND SNACK. SAME DONUT.','WEATHER FOR BREAKFAST.','TWO OF FIVE. STILL SWEET.']),
      ('PB60','banana','banana-first-meal',banana,'My Bruised Banana finally got its first meal.',24,
       ['SOMEONE MISSED BREAKFAST.','BANANA. MEET YOUR FIRST MEAL.','THAT IS ONE REAL FEED.','FIRST FEED. ONE OF FIVE.'])]
    for eid,key,slug,result,title,music,lines in specs:
      prev=load(CAPTURE_Q/(key+'-before.json'))['feedCount'];count=result['creature']['feedCount'];name=result['species']['name']
      rows.append(dict(id=eid,slug=slug,name=name,title=title,duration=8.0,music_start=music,evidence=[key+'_feed'],
        note=f'Fresh public game footage recorded 2 November 2026 in our continuing filming profile. {name}: successful feed progression {prev}/5 to {count}/5.',
        shots=[shot(key+'_bench_before',.2,1.1,1,lines[0],face=True),shot(key+'_feed_click',-.8,1.2,1,lines[1]),shot(key+'_feed_result',-.1,2.3,1,lines[2]),shot(key+'_bench_after',.2,3.4,1,lines[3])]))
    rows.append(dict(id='PB61',slug='new-day-pips',name='Bruised Banana',title='New day. Another 250 game pips for my little crew.',duration=8.0,music_start=13,evidence=['house_claim'],
      note='Fresh recording of the normal daily 250-pip house grant on 2 November 2026. This is a new daily claim in the same public filming profile. Game pips are credits, not money.',
      shots=[shot('banana_bench_after',.2,1.0,1,'NEW DAY. SAME LITTLE CREW.',face=True),shot('house_claim_click',-1.2,1.5,1,'250 FREE GAME PIPS.'),shot('house_claim_result',-.2,2.3,1,'CLAIMED. SNACKS ARE SORTED.'),shot('house_claim_result',1.0,3.2,1,'BANANA APPROVES THIS BUDGET.')]))
    for eid,key,slug,result,choice,music,city,hook,final in [
      ('PB62','london','london-new-roommate',l,lc,10,'London','LONDON FOUND A ROOMMATE.',l['species']['name'].upper()),
      ('PB63','newyork','new-york-fifth-friend',n,nc,38.7,'New York','NEXT SIGNAL: NEW YORK.','FIVE LITTLE ROOMMATES.')]:
      name=result['species']['name']
      rows.append(dict(id=eid,slug=slug,name=name,title=f'{city} scan: {name} joined my bench.',duration=9.2,music_start=music,evidence=[key+'_catch'],
        note=f'Fresh {city} map scan using the {choice["layer"]} layer and successful catch of {name}, recorded 2 November 2026. Coordinates were typed into the public map for remote play. Results are examples, not guaranteed finds.',
        shots=[shot(key+'_bench',.1,1.0,1,hook,face=True),shot(key+'_coordinates',0,1.3,1,f'PIN: {city.upper()}.'),shot(choice['scanKey']+'_result',1.0,1.5,1,'THE SIGNAL ANSWERED.'),shot(key+'_catch_result',-.6,1.9,1,'CAUGHT. COMING HOME.'),shot(key+'_bench',.5,3.5,1,final)]))
    return rows

def build(ep):
    raw=R/'capture/raw-vertical.mp4';clips=[]
    for n,(start,dur,speed,line,y,face) in enumerate(ep['shots']):
        card=Image.new('RGBA',(1080,1920),(0,0,0,0));d=ImageDraw.Draw(card)
        d.rounded_rectangle((35,y,1045,y+140),radius=24,fill=(10,18,24,242))
        b.label(card,line,y+39,b.CREAM,55)
        d.rounded_rectangle((50,1745,1030,1800),radius=9,fill=(6,10,12,230))
        b.label(card,'FRESH GAMEPLAY · 02 NOV 2026 · WAITING SHORTENED',1755,b.CREAM,24)
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
    sources=[raw]+evidence+[CAPTURE_Q/'capture-summary.json',CAPTURE_Q/'initial-owned.json']
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
