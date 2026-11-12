"""Bounded unauthenticated public GETs; no remote code execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import hashlib, json

ROOT = Path(__file__).parent
TASKS = {
    'forge-page': 'https://theagentforge.io/t/npm%3A%40aimarket%2Fwarden',
    'forge-api': 'https://theagentforge.io/api/v1/check?id=npm%3A%40aimarket%2Fwarden',
    'aicom13': 'https://api.github.com/repos/alexar76/aicom/issues/13',
    'aicom13-comments': 'https://api.github.com/repos/alexar76/aicom/issues/13/comments?per_page=100',
    'industrial-requirements': 'https://raw.githubusercontent.com/industrial-platform-ai/industrial-platform-agent-tools/main/aimarket-sentinel/requirements.txt',
    'industrial-adapter': 'https://raw.githubusercontent.com/industrial-platform-ai/industrial-platform-agent-tools/main/gateway/aimarket-federation.mjs',
    'industrial-manifest': 'https://x402-gateway-production-1f21.up.railway.app/ai-market/v2/manifest',
    'industrial-discovery': 'https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json',
    'rugsnare-tree': 'https://api.github.com/repos/Paraphern/rugsnare/git/trees/main?recursive=1',
    'rugsnare-readme': 'https://raw.githubusercontent.com/Paraphern/rugsnare/main/README.md',
    'traits-commit': 'https://api.github.com/repos/isotope13-dev/traits-dev/commits/d28c0c79dfc7aecb94c40acbbc8109ecee26d2ab',
    'shortformkit-data': 'https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/data/servers.json',
    'route-health': 'https://route-verdict-production.up.railway.app/health',
    'recheck-feed': 'https://stall-row-production.up.railway.app/v1/recheck/feed?v=2',
}
SEARCH = {
    'issues-identity': ('issues', '"alexar76" -author:alexar76 -user:alexar76 sort:updated-desc'),
    'issues-domain': ('issues', '"modelmarket.dev" -author:alexar76 -user:alexar76 sort:updated-desc'),
    'commits-hub': ('commits', '"aimarket-hub" -author:alexar76'),
    'commits-warden': ('commits', '"@aimarket/warden" -author:alexar76'),
    'repos-domain': ('repositories', '"modelmarket.dev" in:readme -user:alexar76'),
}
for key, (kind, q) in SEARCH.items():
    TASKS[key] = 'https://api.github.com/search/' + kind + '?' + urlencode({'q':q,'per_page':100,'sort':'updated' if kind != 'commits' else 'committer-date','order':'desc'})

def fetch(item):
    key, url = item
    row = {'key':key, 'url':url, 'method':'GET', 'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0 (public evidence audit; read-only)', 'Accept':'application/json,text/html,text/plain,*/*'}), timeout=40) as r:
            data = r.read(15000000)
            row.update(status=r.status, final_url=r.url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), file=key+'.raw')
            (ROOT/row['file']).write_bytes(data)
    except HTTPError as e:
        data=e.read(100000)
        row.update(status=e.code, error=str(e), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), file=key+'.raw')
        (ROOT/row['file']).write_bytes(data)
    except Exception as e:
        row['error']=str(e)
    return row

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(fetch,TASKS.items()))
    (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
