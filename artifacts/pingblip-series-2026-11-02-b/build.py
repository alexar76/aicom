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
    def shot(key,offset,dur,line,face=False):return (round(m[key]+offset,3),dur,1,line,190,face)
    specs=[
      ('PB64','raccoon','raccoon-third-snack','My Dumpster Raccoon is three snacks into this friendship.',6.69,
       ['THE LITTLE BOSS IS BACK.','THIRD SNACK. SAME ATTITUDE.','ONE MORE REAL FEED.','THREE OF FIVE. SO CLOSE.']),
      ('PB65','donut','donut-third-snack','My Glaze Donut came back for snack number three.',18,
       ['SWEET FACE. BIG APPETITE.','SNACK NUMBER THREE.','FRESH WEATHER. FRESH MEAL.','THREE OF FIVE. STILL SWEET.']),
      ('PB66','banana','banana-second-meal','My Bruised Banana gets its second real meal.',24,
       ['BANANA IS BACK FOR MORE.','SECOND MEAL. LETS GO.','ANOTHER REAL FEED.','TWO OF FIVE. LOOKING GOOD.']),
      ('PB67','dumpling','dumpling-first-meal','First meal for my Angry Dumpling. Still angry.',13,
       ['MY ANGRY LITTLE ROOMMATE.','HIS FIRST REAL MEAL.','FED. STILL JUDGING ME.','ONE OF FIVE. SAME FACE.']),
      ('PB68','cola','cola-first-meal','My Cola Cube finally gets its first meal.',38.7,
       ['THE CUBE REQUESTS A SNACK.','FIRST MEAL FOR COLA CUBE.','THAT COUNTS AS BREAKFAST.','ONE OF FIVE. STAY FIZZY.'])]
    rows=[]
    for eid,key,slug,title,music,lines in specs:
        result=receipt(key+'_feed');before=load(CAPTURE_Q/(key+'-before.json'));after=load(CAPTURE_Q/(key+'-after.json'))
        assert result['creature']['feedCount']==before['feedCount']+1==after['feedCount']
        name=result['species']['name']
        assert after['feedCount']=={'raccoon':3,'donut':3,'banana':2,'dumpling':1,'cola':1}[key]
        rows.append(dict(id=eid,slug=slug,name=name,title=title,duration=8.0,music_start=music,evidence=[key+'_feed'],
          note=f'Fresh gameplay filmed on 2 November 2026, in a new recording after the earlier series. {name}: actual feed progression {before["feedCount"]}/5 to {after["feedCount"]}/5 in our continuing public filming profile.',
          shots=[shot(key+'_bench_before',.2,1.1,lines[0],True),shot(key+'_feed_click',-.8,1.2,lines[1]),shot(key+'_feed_result',-.1,2.3,lines[2]),shot(key+'_bench_after',.2,3.4,lines[3])]))
    if len(sys.argv)>1 and 'PB69' not in sys.argv[1:]:return rows
    sq=A/'qa/capture-scan';sm=load(sq/'marks.json');scan=load(sq/'barcelona_scan_weather-result.json')
    assert scan['httpStatus']==200 and scan['result']['roster'] and scan['recordedAt']>=load(sq/'capture-summary.json')['recordingStartUnix']
    def ss(key,offset,dur,line):return (round(sm[key]+offset,3),dur,1,line,190,False)
    rows.append(dict(id='PB69',slug='barcelona-next-signal',name='Barcelona scan',title='Barcelona answered. My next creature hunt starts here.',duration=9.2,music_start=10,evidence=['barcelona_scan_weather'],captureQ=str(sq),raw=str(R/'capture-scan/raw-vertical.mp4'),
      note='Fresh Barcelona weather-layer map scan recorded 2 November 2026. Coordinates were typed into the public map for remote play. This episode shows a real scan and roster discovery; no catch is shown or claimed. Results are examples, not guaranteed finds.',
      shots=[ss('barcelona_roster_visible',.1,1.0,'NEXT STOP: BARCELONA.'),ss('barcelona_coordinates',0,1.3,'A NEW PIN. A NEW SIGNAL.'),ss('barcelona_roster_visible',1.0,2.4,'BARCELONA ANSWERED.'),ss('barcelona_roster_visible',3.5,4.5,'WHO SHOULD JOIN US NEXT?')]))
    return rows

def build(ep):
    raw=Path(ep.get('raw',R/'capture/raw-vertical.mp4'));cq=Path(ep.get('captureQ',CAPTURE_Q));clips=[]
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
    evidence=[cq/(name+'-result.json') for name in ep['evidence']]
    sources=[raw]+evidence+[cq/'capture-summary.json',cq/'initial-owned.json']
    desc=ep['note']+'\nWaiting shortened; all game footage comes from this fresh session.\n\nGet your pet free through the game link on @PingBlip.\nhttps://pingblip.com/\nYour first creature is a surprise; the creatures and map results shown are examples.\nGame pips are in-game credits, not money.\n\nMusic: PingBlip original, AI-generated.\n#PingBlip #BrowserGame #CreatureCollector'
    row={**ep,'kind':'gameplay','freshGameplay':True,'recordedAtUtc':load(cq/'capture-summary.json')['recordedAtUtc'],'file':str(out.relative_to(P)),
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
