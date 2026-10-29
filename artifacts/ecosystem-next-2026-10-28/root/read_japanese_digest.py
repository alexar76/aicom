"""Inspect public digest HTML as text. Do not execute scripts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.text=[]; self.links=[]; self.meta=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='a' and a.get('href'): self.links.append(a['href'])
        if tag=='meta' and (a.get('name') or a.get('property')): self.meta.append(a)
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, text):
        if not self.skip:self.text.append(text)

def read(url):
    out={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 public source research'}),timeout=25) as response:
            raw=response.read();out.update(status=response.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),final_url=response.url)
        p=Page();p.feed(raw.decode('utf-8','replace'));plain=' '.join(' '.join(p.text).split())
        out['metadata']=p.meta
        out['source_links']=[link for link in p.links if any(needle in link.lower() for needle in ['qwezzy','alexar76','modelmarket','about','feed','policy','2026/10/'])]
        out['contexts']=[]
        for needle in ['45%', 'HISTOR','histor.modelmarket','AIで','自動生成','AI生成','生成AI','免責','出典','著作権']:
            for match in list(re.finditer(re.escape(needle),plain))[:2]:
                out['contexts'].append({'needle':needle,'text':plain[max(0,match.start()-100):match.start()+700]})
    except urllib.error.HTTPError as error:out.update(status=error.code,error=str(error))
    except Exception as error:out.update(status=None,error=str(error))
    return out

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(read,['https://ai-outline.com/2026/10/21/','https://ai-outline.com/']))
    (Path(__file__).resolve().parent/'japanese-digest-evidence.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False)[:15000])
