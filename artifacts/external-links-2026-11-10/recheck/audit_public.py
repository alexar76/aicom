"""Bounded public GET-only source/backlink capture. No credentials or tool invokes."""
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
UA = 'AICOM-public-readonly-link-audit/2026-11-10'
SOURCES = [
 ('a2aregistry', 'https://a2aregistry.org/agents/841eea85-51d4-450c-b35a-086534dc08f6/'),
 ('a2a-registry', 'https://www.a2a-registry.org/agent/dev.modelmarket.modelmarketdev'),
 ('agentsearch', 'https://agentsearch.luthersystems.com/agent/modelmarket.dev'),
 ('agenstry', 'https://agenstry.com/agents/modelmarket.dev'),
 ('agentrank-metis', 'https://agentrank-ai.com/tool/alexar76--metis/'),
 ('agentrank-hub', 'https://agentrank-ai.com/tool/alexar76--aimarket-hub/'),
 ('agentrank-agent', 'https://agentrank-ai.com/tool/alexar76--aimarket-agent/'),
 ('agentsshipped', 'https://agentsshipped.com/l/alexar76-aicom'),
 ('anclum-plugins', 'https://anclum.com/zh/s/alexar76-aimarket-plugins/'),
 ('one-gateway', 'https://1gateway.dev/market/modelmarket.dev'),
 ('lupariel', 'https://lupariel.com/fichas/aimarket-hub/'),
 ('apis-attested', 'https://apis.io/providers/attestedmemory-net/'),
 ('karatum', 'https://karatum.com/ratings/kt_03befd45aaa86be2de6ceff9'),
 ('aer', 'https://agenteconomy.report/s/modelmarket.dev'),
 ('vouch', 'https://vouch-protocol.com/agent-trust-index/'),
 ('verify-mcp', 'https://verifymcp.io/servers/alexar76-aimarket-hub/modelmarket'),
 ('hlido', 'https://hlido.eu/passport/alexar76-aimarket-plugins/'),
 ('odel-hub', 'https://odel.app/modules/alexar76/aimarket-hub'),
 ('mcpbeat', 'https://mcpbeat.com/mcp-servers/alexar76/aimarket-hub/'),
 ('gemivo', 'https://ainews.gemivo.de/news/we-found-331-mcp-tool-list-changes-in-one-week-that-only-cmw03yqv3005'),
 ('teckdeck', 'https://teckdeck.io/posts/we-found-331-mcp-tool-list-changes-in-one-week-that-only-moved-a-date-each-one-costs-a-prompt-cache-write'),
 ('webpulse', 'https://wpnews.pro/news/we-ran-three-mcp-security-scanners-on-a-tool-poisoning-benchmark-and-986-real'),
 ('linda-reply', 'https://mailarchive.ietf.org/arch/msg/dawn/6m1_jcurI0F0_LadffO71f0d4m8/'),
]

class Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]; self.parts=[]; self.skip=0; self.title=False; self.titles=[]; self.in_head=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='head': self.in_head=True
        if tag=='title' and self.in_head: self.title=True
        if tag=='a' and a.get('href'): self.links.append({'href':a['href'],'rel':a.get('rel','')})
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip: self.skip-=1
        if tag=='title': self.title=False
        if tag=='head': self.in_head=False
    def handle_data(self,d):
        if not self.skip and d.strip(): self.parts.append(d.strip())
        if self.title: self.titles.append(d.strip())

def owned(u):
    p=urllib.parse.urlsplit(u); host=(p.hostname or '').lower(); path=p.path.lower()
    if any(host==d or host.endswith('.'+d) for d in ('modelmarket.dev','attestedmemory.net','magic-ai-factory.com','alexar76.github.io','pingblip.com')): return True
    if host in ('github.com','raw.githubusercontent.com','huggingface.co','dev.to','medium.com') and ('/alexar76/' in path or path.startswith('/@alexar76/')): return True
    if host=='www.npmjs.com' and '/@aimarket/' in path: return True
    return False

def fetch(url,limit):
    row={'requested_url':url,'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/json,text/plain;q=0.9,*/*;q=0.1'})
    try: response=urllib.request.urlopen(req,timeout=20)
    except urllib.error.HTTPError as e: response=e
    except Exception as e:
        row['error']=f'{type(e).__name__}: {e}'; return row,None
    with response:
        body=response.read(limit+1)
        row.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),headers={k:response.headers.get(k) for k in ('Date','Last-Modified','ETag','Content-Length','X-Robots-Tag') if response.headers.get(k)})
    row['truncated']=len(body)>limit
    body=body[:limit]
    row.update(captured_bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
    return row,body

def source(item):
    name,url=item
    row,body=fetch(url,6_000_000); row['name']=name
    if body is None: return row
    file=ROOT/(name+'.html');file.write_bytes(body);row['file']=file.name
    p=Extract()
    try: p.feed(body.decode('utf-8',errors='replace'))
    except Exception as e: row['parse_error']=str(e)
    row['title']=' '.join(p.titles)
    text='\n'.join(p.parts);(ROOT/(name+'.txt')).write_text(text)
    links=[]
    for a in p.links:
        u=urllib.parse.urljoin(row['final_url'],html.unescape(a['href']))
        if owned(u): links.append({'target_url':u,'rel':a['rel']})
    row['owned_links']=list({(x['target_url'],x['rel']):x for x in links}.values())
    row['identity_text_occurrences']=len(re.findall('alexar76|modelmarket\\.dev|attestedmemory\\.net',text,re.I))
    return row

def target(item):
    index,url=item
    row,body=fetch(url,120_000)
    if body is not None:
        f=ROOT/f'target-{index:03d}.raw';f.write_bytes(body);row['file']=f.name
        if 'text/html' in row.get('content_type',''):
            p=Extract();p.feed(body.decode('utf-8',errors='replace'));row['title']=' '.join(p.titles)
    return row

def main():
    with cf.ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(source,SOURCES))
    (ROOT/'source-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    targets=sorted({urllib.parse.urldefrag(a['target_url']).url for r in rows if r.get('status')==200 and not r.get('truncated') for a in r.get('owned_links',[])})
    # Avoid paid/invoke, login, submissions and large binary downloads. GET checks only.
    targets=[u for u in targets if urllib.parse.urlsplit(u).scheme in ('http','https') and not re.search(r'\.(zip|gz|png|jpg|svg|pdf)(\?|$)|/login|/invoke|/x402/',u)]
    with cf.ThreadPoolExecutor(max_workers=5) as pool: checked=list(pool.map(target,enumerate(targets)))
    (ROOT/'target-index.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2)+'\n')
    summary={'sources':len(rows),'source_status_counts':{str(s):sum(x.get('status')==s for x in rows) for s in sorted({x.get('status') for x in rows if x.get('status') is not None})},'source_errors':sum('error' in x for x in rows),'source_pages_with_owned_href':sum(bool(x.get('owned_links')) and x.get('status')==200 for x in rows),'target_gets':len(checked),'target_status_counts':{str(s):sum(x.get('status')==s for x in checked) for s in sorted({x.get('status') for x in checked if x.get('status') is not None})},'target_errors':sum('error' in x for x in checked)}
    (ROOT/'http-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
