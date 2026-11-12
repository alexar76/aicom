"""Read-only capture of selected public pages; never runs source code or calls MCP tools."""
import concurrent.futures, datetime, hashlib, html, json, re, urllib.request, urllib.error
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'mcpindex-hub': 'https://mcpindex.ai/server/io-github-alexar76-aimarket-hub',
    'mcpbeat-weather': 'https://mcpbeat.com/mcp-servers/modelmarket/weather/',
    'protocolprobe-weather': 'https://protocolprobe.com/mcp/servers/dev.modelmarket/weather',
    'a2aregistry-hub': 'https://a2aregistry.org/agents/841eea85-51d4-450c-b35a-086534dc08f6/',
    'tracevero-gateway': 'https://tracevero.com/mcp/io-github-alexar76-aimarket-mcp',
    'lightnow-hub': 'https://lightnow.ai/servers/io.github.alexar76/aimarket-hub',
    'odel-attested': 'https://odel.app/modules/alexar76/attested-memory',
    'odel-hub': 'https://odel.app/modules/alexar76/aimarket-hub',
    'odel-plugins': 'https://odel.app/modules/alexar76/aimarket-plugins',
    'apis-attested': 'https://apis.io/providers/attestedmemory-net/',
    'glama-weather': 'https://glama.ai/mcp/connectors/dev.modelmarket/weather',
    'glama-gateway': 'https://glama.ai/mcp/servers/alexar76/aimarket-mcp',
    'libhunt-gaia': 'https://www.libhunt.com/r/alexar76/gaia',
    'mcprepository-author': 'https://mcprepository.com/alexar76',
    'hlido-passport': 'https://hlido.eu/passport/alexar76-aimarket-plugins/',
    'hlido-scorecard': 'https://raw.githubusercontent.com/ankitkapur1992-hlido/hlido-public/main/scorecards/alexar76-aimarket-plugins.json',
    'industrial-requirements': 'https://raw.githubusercontent.com/industrial-platform-ai/industrial-platform-agent-tools/main/aimarket-sentinel/requirements.txt',
    'industrial-discovery': 'https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json',
    'agent-exec-discovery': 'https://agent-exec.448c.org/.well-known/ai-market.json',
    'agent-exec-manifest': 'https://agent-exec.448c.org/ai-market/v2/manifest',
    'bracha-readme': 'https://raw.githubusercontent.com/bracha55555-hue/aimarket/main/README.md',
    'bracha-requirements': 'https://raw.githubusercontent.com/bracha55555-hue/aimarket/main/requirements.txt',
    'sep163-readme': 'https://raw.githubusercontent.com/sep163/aimarket-agents/main/README.md',
    'sep163-requirements': 'https://raw.githubusercontent.com/sep163/aimarket-agents/main/requirements.txt',
}

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('href'):
            self.links.append({'href':attrs['href'],'rel':attrs.get('rel')})
    def handle_data(self, value): self.text.append(value)

def capture(item):
    name, url=item
    row={'id':name,'source_url':url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET'}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Public ecosystem link research/2026-11-10','Accept':'text/html,application/json,text/plain;q=0.9'})
        try:
            resp=urllib.request.urlopen(req,timeout=35)
        except urllib.error.HTTPError as exc: resp=exc
        with resp:
            body=resp.read(4_000_001)
            row.update(status=resp.code,final_url=resp.url,content_type=resp.headers.get('content-type'),bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),complete=len(body)<=4_000_000)
        file=ROOT/'bodies'/f'{name}.body'
        file.parent.mkdir(exist_ok=True)
        file.write_bytes(body)
        row['body_path']=str(file.relative_to(ROOT))
        value=body.decode('utf-8','replace')
        parser=Links(); parser.feed(value)
        row['ecosystem_href']=[l for l in parser.links if re.search(r'(?:alexar76|modelmarket\.dev|attestedmemory\.net|magic-ai-factory\.com|independentai\.network)',l['href'],re.I)]
        row['exact_mentions']=sorted(set(re.findall(r'https?://[^\s\x22\x27<>]+(?:alexar76|modelmarket\.dev)[^\s\x22\x27<>]*',value)))[:100]
        if name in ('industrial-requirements','bracha-requirements','sep163-requirements'): row['text']=value
        if name in ('industrial-discovery','agent-exec-discovery','agent-exec-manifest','hlido-scorecard'):
            try: row['json']=json.loads(value)
            except ValueError: pass
        text=' '.join(parser.text)
        row['selected_contexts']=[]
        for term in ('quality','last tested','last checked','first seen','listed from','Task verified','Checks','review due','2026-11-10','2026-11-09','Observations','answered','not call','no server','tools/list','aimarket-hub','modelmarket.dev'):
            match=re.search(re.escape(term),text,re.I)
            if match:
                row['selected_contexts'].append({'term':term,'context':text[max(0,match.start()-70):match.end()+240]})
    except Exception as exc: row['error']=f'{type(exc).__name__}: {exc}'
    return row

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(capture,SOURCES.items()))
    (ROOT/'verification.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'id':r['id'],'status':r.get('status'),'href_count':len(r.get('ecosystem_href',[])),'bytes':r.get('bytes'),'error':r.get('error')} for r in rows],ensure_ascii=False,indent=2))
