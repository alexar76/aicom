"""Public GET-only response delta, after the previous research snapshot."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
SINCE = '2026-10-28T13:31:57Z'
TASKS = [
    ('mcp3431', 'https://api.github.com/repos/modelcontextprotocol/modelcontextprotocol/issues/3431/comments?per_page=100', 'comments'),
    ('vulnetix5', 'https://api.github.com/repos/Vulnetix/advisory-database/issues/5/comments?per_page=100', 'comments'),
    ('agentmesh561', 'https://api.github.com/repos/google/agentmesh/issues/561/comments?per_page=100', 'comments'),
    ('skills-pr14', 'https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14', 'pull'),
    ('dev-localhost', 'https://dev.to/api/articles/alexar76/why-our-mcp-server-stopped-trusting-localhost-by-default-26jm', 'article'),
    ('dev-independent-captures', 'https://dev.to/api/articles/alexar76/same-mcp-version-different-tools-what-two-independent-captures-revealed-2p6d', 'article'),
]

def read(task):
    key, url, kind = task
    out = {'key': key, 'url': url, 'method': 'GET', 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 public research'}), timeout=25) as response:
            raw = response.read(); out.update(status=response.status, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), rate_remaining=response.headers.get('x-ratelimit-remaining'))
        data=json.loads(raw)
        if kind=='comments':
            out['visible_comments']=len(data)
            out['created_after_previous_snapshot']=[{k:row.get(k) for k in ['id','html_url','created_at','updated_at','body']} | {'author':row.get('user',{}).get('login')} for row in data if row.get('created_at','')>SINCE]
            out['updated_after_previous_snapshot']=[{'id':row['id'],'html_url':row['html_url'],'updated_at':row.get('updated_at')} for row in data if row.get('updated_at','')>SINCE and row.get('created_at','')<=SINCE]
        elif kind=='pull':
            out['selected']={k:data.get(k) for k in ['html_url','state','merged','merged_at','updated_at','comments','review_comments','head','base']}
            for field in ['head','base']:
                ref=out['selected'].get(field) or {};out['selected'][field]={k:ref.get(k) for k in ['label','ref','sha']}
        else:
            out['selected']={k:data.get(k) for k in ['id','url','title','published_at','comments_count','public_reactions_count']}
    except urllib.error.HTTPError as error:out.update(status=error.code,error=str(error))
    except Exception as error:out.update(status=None,error=str(error))
    return out

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(read,TASKS))
    (ROOT/'current-response-delta.json').write_text(json.dumps({'since_utc':SINCE,'records':records},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(records,ensure_ascii=False))
