"""Read-only public-source refresh; no account credentials or write requests."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
PRIOR = ROOT.parents[1] / 'docs/evidence/external-signals-2026-10-27'
selected = {
    'dev-articles.json', 'mcp3431-comments.json', 'agentmesh561-comments.json',
    'vulnetix5-comments.json', 'pr14.json', 'pr14-comments.json',
    'pr14-reviews.json', 'pr14-review-comments.json', 'rugsnare-readme.json',
    'rugsnare-shopify.json', 'hn-histor-story.json', 'hn-histor-thread.json',
    'hn-domain-search.json', 'hn-owner-search.json',
}
prior_index = json.loads((PRIOR / 'verification-index.json').read_text())
targets = [(x['file'], x['url']) for x in prior_index['records']
           if x['file'] in selected or x['file'].startswith('vulnetix-GCVE-')]
targets += [
    ('github-readme-mentions.json', 'https://api.github.com/search/repositories?' + urllib.parse.urlencode({'q':'alexar76 in:readme -user:alexar76','per_page':100})),
    ('github-recent-mentions.json', 'https://api.github.com/search/issues?' + urllib.parse.urlencode({'q':'"alexar76" -author:alexar76 updated:>=2026-10-27','sort':'updated','per_page':100})),
    ('github-recent-domain.json', 'https://api.github.com/search/issues?' + urllib.parse.urlencode({'q':'"modelmarket.dev" -author:alexar76 updated:>=2026-10-27','sort':'updated','per_page':100})),
]

def read(pair):
    name, url = pair
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {'file':name, 'url':url, 'retrieved_at':now, 'method':'GET'}
    req = urllib.request.Request(url, headers={'User-Agent':'alexar76-public-mention-review/1.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = response.read()
            record.update(status=response.status, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), final_url=response.url)
            data = json.loads(body)
            (ROOT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    except urllib.error.HTTPError as exc:
        record.update(status=exc.code, error=str(exc))
    except Exception as exc:
        record.update(status=None, error=str(exc))
    return record

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(read, targets))

article_path = ROOT/'dev-articles.json'
if article_path.exists():
    articles = json.loads(article_path.read_text())
    comments = [(f'dev-comments-{a["id"]}.json',f'https://dev.to/api/comments?a_id={a["id"]}')
                for a in articles if a.get('comments_count',0)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records += list(pool.map(read, comments))

(ROOT/'public-api-index.json').write_text(json.dumps({'records':records}, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'requests':len(records),'status_counts':{str(s):sum(x.get('status')==s for x in records) for s in set(x.get('status') for x in records)},'errors':[x for x in records if x.get('status')!=200]},ensure_ascii=False,indent=2))
