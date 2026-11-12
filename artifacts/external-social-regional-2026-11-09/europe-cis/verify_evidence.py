from pathlib import Path
from collections import Counter
import hashlib,json
ROOT=Path(__file__).parent
rows=[]
for f in ['http-index.json','followup-index.json']:rows+=json.loads((ROOT/f).read_text())
verified=0
for r in rows:
 if 'file' not in r:continue
 b=(ROOT/r['file']).read_bytes()
 assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],r['key']
 verified+=1
q=json.loads((ROOT/'query-index.json').read_text());assert len(q)==25
post=json.loads((ROOT/'radyz-known-post.raw').read_text())
assert post['date'].startswith('2026-10-22') and post['comment_status']=='closed'
assert json.loads((ROOT/'radyz-known-comments.raw').read_text())==[]
html=(ROOT/'habr-candidate.raw').read_text()
assert 'github.com/W3OSC/skill-warden' in html
assert all(s not in html.lower() for s in ['modelmarket.dev','alexar76','attestedmemory.net'])
out={'proposed_web_queries':len(q),'web_response_batches':7,'direct_gets':len(rows),
     'statuses':dict(Counter(str(r.get('status','timeout_or_error')) for r in rows)),
     'bodies_hash_verified':verified,'radyz_known_not_new':True,'radyz_comments_closed_empty':True,
     'habr_false_positive_excluded':True,'new_independent_regional_mentions':0}
(ROOT/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
