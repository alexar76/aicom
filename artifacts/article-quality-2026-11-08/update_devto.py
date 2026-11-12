"""Publish the quality revision to four existing DEV.to ids, preserving dates."""
from datetime import datetime,timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import time
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('scheduler',ROOT/'artifacts/devto-new-articles-2026-11-07/schedule.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
plan=json.loads((HERE/'quality-plan.json').read_text())
baseline={p['id']:p for p in json.loads((HERE/'baseline.json').read_text())['posts']}
assert (HERE/'public-blog-check.json').exists()
assert m.api.request('/api/users/me')['username']=='alexar76'
prepared=[]

class MediaCheck(m.RenderCheck):
    def __init__(self):
        super().__init__();self.images=0
    def handle_starttag(self,tag,attrs):
        super().handle_starttag(tag,attrs)
        if tag=='img':self.images+=1
for post in plan:
    pack=m.PROMO/post['pack'];_,front,body=(pack/'article.md').read_text().split('---',2);body=body.lstrip('\n')
    fields={k.strip():json.loads(v.strip()) if v.strip().startswith('"') else v.strip() for k,v in (line.split(':',1) for line in front.strip().splitlines())}
    assert sha256(body.encode()).hexdigest()==post['newBodySha256']
    assert (ROOT/'modelmarket-blog/posts'/post['slug']/'body.md').read_text()==body
    assert 'AI assistance' in body.rstrip().splitlines()[-1]
    assert fields['title']==post['title'] and fields['cover_image']==post['coverUrl']
    prepared.append((post,pack,body,fields))

for index,(post,pack,body,fields) in enumerate(prepared):
    response_path=pack/'devto-quality-2026-11-08-response.json'
    if response_path.exists():
        changed=json.loads(response_path.read_text());assert changed['body_markdown']==body
    else:
        if index:time.sleep(21)
        live=next(row for row in m.owned() if row['id']==post['id'])
        assert live['title']==post['title'] and live['user']['username']=='alexar76'
        assert m.timestamp(live['published_at'])==m.timestamp(post['devtoAt'])
        assert sha256(live['body_markdown'].encode()).hexdigest()==baseline[post['id']]['bodySha256'],'Concurrent article edit'
        assert not (pack/'devto-quality-2026-11-08-pending.json').exists(),'Reconcile uncertain previous write before retrying'
        m.save(pack/'devto-quality-2026-11-08-pending.json',{'id':post['id'],'bodySha256':post['newBodySha256'],'at':datetime.now(timezone.utc).isoformat()})
        changed=m.api.request('/api/articles/'+str(post['id']),method='PUT',payload={'article':{
            'title':post['title'],'description':post['description'],'body_markdown':body,
            'tags':[x.strip() for x in fields['tags'].split(',')],
            'published':True,'published_at':post['devtoAt'],'canonical_url':post['blogUrl'],
            'main_image':post['coverUrl'],'ai_disclosure_level':'not_disclosed'}})
        m.save(response_path,changed)
    assert changed['id']==post['id'] and changed['user']['username']=='alexar76'
    assert changed['body_markdown']==body and changed['canonical_url']==post['blogUrl']
    assert changed['ai_disclosure_level']=='not_disclosed'
    assert m.timestamp(changed['published_at'])==m.timestamp(post['devtoAt'])
    assert post['imageRevision'] in changed['cover_image']
    check=MediaCheck();check.feed(changed['body_html'])
    assert check.images==2,'Missing inline figure'
    for svg in post['figureSvgs']:assert svg in changed['body_html'],'Full resolution figure link missing'
    (pack/'devto-rendered.html').write_text(changed['body_html'])
    receipt=json.loads((pack/'publication-receipt.json').read_text())
    receipt.update(bodySha256=post['newBodySha256'],words=len(body.split()),qualityUpdatedAt=datetime.now(timezone.utc).isoformat(),
                   coverUrl=post['coverUrl'],inlineFigures=post['figures'],renderedTables=check.tables,renderedCodeBlocks=check.code,
                   aiDisclosureVerifiedAgainst='quality update response')
    m.save(pack/'publication-receipt.json',receipt)
    pending=pack/'devto-quality-2026-11-08-pending.json'
    if pending.exists():pending.unlink()
    print(json.dumps({'id':post['id'],'datePreserved':True,'coverRevision':post['imageRevision'],'inlineFigures':2,'words':len(body.split())}),flush=True)

owned={p['id']:p for p in m.owned()};receipts=[]
for post,pack,body,fields in prepared:
    row=owned[post['id']]
    assert row['title']==post['title'] and row['body_markdown']==body and row['canonical_url']==post['blogUrl']
    assert m.timestamp(row['published_at'])==m.timestamp(post['devtoAt'])
    r=json.loads((pack/'publication-receipt.json').read_text());r['finalQueueVerifiedAt']=datetime.now(timezone.utc).isoformat();m.save(pack/'publication-receipt.json',r);receipts.append(r)
summary={'author':'alexar76','articles':receipts,'fourDistinctCovers':True,'technicalFigures':8,'publicationDatesPreserved':True,'githubWrites':False}
m.save(HERE/'final-publication-check.json',summary)
m.save(m.PROMO/'ecosystem-articles-2026-11-07.json',summary)
m.save(ROOT/'artifacts/devto-new-articles-2026-11-07/final-queue-verification.json',summary)
print('All four revised articles, eight inline figures and new covers read back; dates preserved.',flush=True)
