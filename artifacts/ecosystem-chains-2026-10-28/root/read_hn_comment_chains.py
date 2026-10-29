"""Read public HN full-text comment searches; never authenticate or post."""
import concurrent.futures
import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
QUERIES = ['modelmarket.dev', 'alexar76', 'histor.modelmarket.dev', 'AIMarket', 'WARDEN MCP', 'github.com/alexar76/', 'argus3', 'HISTOR dataset']

def read(query):
    params = {'query': '"'+query+'"', 'tags': 'comment', 'restrictSearchableAttributes': 'comment_text', 'hitsPerPage': 100, 'typoTolerance': 'false', 'removeWordsIfNoResults': 'none', 'advancedSyntax': 'true'}
    url = 'https://hn.algolia.com/api/v1/search?' + urllib.parse.urlencode(params)
    record = {'query': query, 'url': url, 'method': 'GET', 'retrieved_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (public source research)'})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            record.update(status=response.status, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        data = json.loads(raw)
        record.update(nbHits=data.get('nbHits'), nbPages=data.get('nbPages'), hits=[])
        for hit in data.get('hits', []):
            plain = html.unescape(re.sub('<[^>]+>', ' ', hit.get('comment_text') or ''))
            needles = ['modelmarket', 'alexar76', 'histor', 'aimarket', 'argus3', 'warden']
            pos = min([p for needle in needles if (p := plain.lower().find(needle)) >= 0], default=0)
            record['hits'].append({'id': hit.get('objectID'), 'author': hit.get('author'), 'created_at': hit.get('created_at'), 'story_id': hit.get('story_id'), 'story_title': hit.get('story_title'), 'story_url': hit.get('story_url'), 'comment_url': 'https://news.ycombinator.com/item?id=' + hit.get('objectID', ''), 'context': ' '.join(plain[max(0,pos-120):pos+650].split())})
    except urllib.error.HTTPError as error:
        record.update(status=error.code, error=str(error))
    except Exception as error:
        record.update(status=None, error=str(error))
    return record

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(read, QUERIES))
    (ROOT/'hn-comment-search-exact.json').write_text(json.dumps({'scope': 'Public HN Algolia comment text search, exact quoted query, typoTolerance false and removeWordsIfNoResults none. One page per query. Hits are discovery candidates, not all attributable to our ecosystem.', 'records': records}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps([{'query': row['query'], 'status': row['status'], 'hits': row.get('nbHits'), 'pages': row.get('nbPages'), 'authors': sorted(set(hit['author'] for hit in row.get('hits', []) if hit.get('author')))} for row in records], ensure_ascii=False))
