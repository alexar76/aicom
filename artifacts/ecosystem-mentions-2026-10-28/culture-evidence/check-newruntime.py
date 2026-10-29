import urllib.request, json, datetime, hashlib, pathlib
from html.parser import HTMLParser

class Extract(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag=='a':
            d=dict(attrs)
            if d.get('href'):self.links.append(d['href'])
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,s):
        if not self.skip and s.strip():self.parts.append(s.strip())

url='https://newruntime.com/readers/histor/'
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public mention verification)'})
with urllib.request.urlopen(req,timeout=25) as r:
    data=r.read(); status=r.status; final=r.url
p=Extract(); p.feed(data.decode('utf-8'))
rec={'url':url,'final_url':final,'status':status,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'links':list(dict.fromkeys(p.links)),'short_relevant_extracts':[]}
for i,t in enumerate(p.parts):
    if any(k in t.lower() for k in ('histor','modelmarket','171','request','documentation','operator','2026-10-','method','user-agent','user agent','read-only','discovery','unknown')):
        rec['short_relevant_extracts'].append(' | '.join(p.parts[max(0,i-1):i+3]))
path=pathlib.Path(__file__).parent/'newruntime-facts.json'
path.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
print(json.dumps(rec,ensure_ascii=False,indent=2))
