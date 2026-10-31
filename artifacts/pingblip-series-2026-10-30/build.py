from pathlib import Path
import importlib.util,json,subprocess,hashlib
from PIL import Image,ImageDraw
P=Path('/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/blip/youtube-season-something-pinged')
R=P/'v15-mini-stories'
for d in ['work','final','qa']:(R/d).mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('old',P/'v14-action-first/source/build_batch.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.W=R/'work'
episodes=[('PB44','snack-tax','I got a pet. It sent me a bill.','v10-weird-one/capture-session',[(42.8,1.2,1,'MY NEW ROOMMATE'),(36.15,1.4,1,'RENT? 50 PIPS.'),(37.5,1.8,2.2,'PAYING THE SNACK TAX'),(42.9,2.4,1,'ONE FEED. ALREADY THE BOSS.')]),('PB45','final-snack','One snack away. Then this happened.','v9-gameplay-funnel/capture-evolve',[(20,1,1,'ONE SNACK LEFT.'),(29.75,1.2,1,'DO WE DO IT?'),(30.85,1.7,3,'OKAY. HERE GOES.'),(37.5,2.8,1,'THAT IS MY GOBLIN?!')]),('PB46','breakfast','My goblin has one morning rule.','v10-weird-one/capture-wake',[(11.5,1.3,1,'NO TALKING.'),(22.8,1.1,1,'BREAKFAST FIRST.'),(24,1.7,3,'FAIR ENOUGH.'),(29.8,2.6,1,'NOW WE CAN BE FRIENDS.')])]
rows=[]
for eid,slug,title,capture,shots in episodes:
 clips=[]
 for n,(start,dur,speed,line) in enumerate(shots):
  card=Image.new('RGBA',(1080,1920),(0,0,0,0));d=ImageDraw.Draw(card);d.rounded_rectangle((35,190,1045,325),radius=24,fill=(10,18,24,235));b.label(card,line,228,b.CREAM,47);b.label(card,'REAL GAMEPLAY · WAITING SHORTENED',1690,b.CREAM,27)
  if n==len(shots)-1:b.label(card,'YOUR LITTLE WEIRDO · LINK IN PROFILE',1570,b.LIME,32)
  png=R/'work'/f'{eid}-{n}.png';card.save(png);clip=R/'work'/f'{eid}-{n}.mp4'
  crop='crop=900:1600:90:160,scale=1080:1920' if n%2==0 else 'scale=1080:1920'
  b.run(['ffmpeg','-v','error','-y','-ss',start,'-i',P/capture/'raw-vertical.mp4','-loop','1','-i',png,'-filter_complex_threads','1','-filter_complex',f'[0:v]setpts=(PTS-STARTPTS)/{speed},{crop},fps=30,tpad=stop_mode=clone:stop_duration=2[v];[v][1:v]overlay=0:0,format=yuv420p[o]','-map','[o]','-an','-t',dur,'-c:v','libx264','-crf','18','-preset','veryfast',clip]);clips.append(clip)
 concat=R/'work'/f'{eid}.txt';concat.write_text(''.join(f"file '{p}'\n" for p in clips));silent=R/'work'/f'{eid}.mp4';b.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',silent]);out=R/'final'/f'{eid}-{slug}.mp4';duration=sum(s[1] for s in shots);b.mux({'music_start':18},silent,duration,out)
 subprocess.run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'],check=True)
 sheet=Image.new('RGB',(1080,480))
 for n,t in enumerate([0,1.5,3.5,duration-.4]):
  frame=R/'qa'/f'{eid}-{n}.jpg';b.run(['ffmpeg','-v','error','-y','-ss',t,'-i',out,'-frames:v','1','-vf','scale=270:480',frame]);sheet.paste(Image.open(frame),(n*270,0))
 sheet.save(R/'qa'/f'{eid}.jpg');rows.append(dict(id=eid,title=title,file=str(out.relative_to(P)),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),duration=duration,capture=capture,shots=shots));print(eid,flush=True)
(R/'final/manifest.json').write_text(json.dumps(rows,indent=2))
