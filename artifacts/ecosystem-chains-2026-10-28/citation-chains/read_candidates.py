from pathlib import Path
import concurrent.futures, hashlib, json, re, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BASE = Path(__file__).resolve().parent
class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.meta=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='a' and d.get('href'): self.links.append(d['href'])
        if tag=='meta': self.meta.append(d)
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

URLS = [
 ('hubwiz-tools','https://www.hubwiz.com/blog/mcp-tool-count-1932-runs-measured/'),
 ('hubwiz-payments','https://www.hubwiz.com/blog/agent-payment-security-x402-guardrails/'),
 ('hubwiz-delivery','https://www.hubwiz.com/blog/agent-delivery-verification-gates/'),
 ('hubwiz-restarts','https://www.hubwiz.com/blog/agent-restart-replay-idempotency-retro/'),
 ('feinterview-tools','https://feinterview.poetries.top/ai-monitor/news/how-many-tools-should-an-mcp-server-have-i-measured-5-to-100-in-claude-code-codex-and'),
 ('zalize-plugins','https://mcp.zalize.com/s/alexar76-aimarket-plugins'),
]
def read(item):
    key,url=item; r={'key':key,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (AICOM public-source research)'}),timeout=25) as f:
            raw=f.read();r.update(status=f.status,final_url=f.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        p=Parser();p.feed(raw.decode('utf-8','replace'));txt=' '.join(' '.join(p.parts).split())
        r['identifiers']={s:len(re.findall(re.escape(s),txt,re.I)) for s in ['alexar76','modelmarket.dev','HISTOR','WARDEN','AICOM','1932','1,932','25 微秒']}
        r['contexts']={}
        for s in ['alexar76','modelmarket.dev','HISTOR','WARDEN','AICOM','来源','原创','来源文章','启发','复盘','Tools','heuristic']:
            hits=list(re.finditer(re.escape(s),txt,re.I))[:3]
            if hits:r['contexts'][s]=[txt[max(0,m.start()-90):m.end()+330] for m in hits]
        r['meta']=[m for m in p.meta if any(t in str(m).lower() for t in ['title','description','publish','modified','author','type'])]
        r['source_links']=[u for u in p.links if any(s in u.lower() for s in ['dev.to/','github.com/','modelmarket','histor','hubwiz','feinterview','about','methodology'])]
        # Full page text is deliberately not retained; only attribution and selected short context.
    except Exception as e:r.update(status=getattr(e,'code',None),error=str(e))
    (BASE/(key+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');return r

if __name__=='__main__':
    rows=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(read,URLS))
    (BASE/'candidate-http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False))
