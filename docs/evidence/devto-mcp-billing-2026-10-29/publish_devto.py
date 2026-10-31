"""Publish exactly the user-approved synthetic MCP billing article as alexar76; no GitHub writes."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import struct
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT.parent / 'PromoMaterials/devto/mcp-hidden-billing-2026-10-29'
STATE = PACK / 'devto-publication.json'
BASE = 'https://modelmarket.dev/blog/media/mcp-hidden-billing-2026-10-29/'
TITLE = 'Our MCP probe missed the paid default'
spec = importlib.util.spec_from_file_location('existing_devto_client', ROOT/'docs/growth/publication-2026-10-25/devto_publish.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

def now():
    return datetime.now(timezone.utc).isoformat()

def save(state):
    temporary = STATE.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(STATE)

class RenderCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images=[];self.links=[];self.tables=0;self.details=0;self.code=0
        self.code_text=[];self.pre_depth=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img':self.images.append({'src':a.get('src'),'alt':a.get('alt')})
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        self.tables+=tag=='table';self.details+=tag=='details';self.code+=tag=='pre'
        if tag=='pre':self.pre_depth+=1;self.code_text.append('')
    def handle_endtag(self,tag):
        if tag=='pre':self.pre_depth-=1
    def handle_data(self,value):
        if self.pre_depth:self.code_text[-1]+=value

def prepared():
    text=(PACK/'article.md').read_text()
    _,front,body=text.split('---',2)
    fields={k.strip():v.strip().strip('"') for k,v in (line.split(':',1) for line in front.strip().splitlines())}
    assert fields['title']==TITLE and fields['published']=='false'
    cover,body=body.lstrip('\n').split('\n\n',1)
    assert cover.startswith('![') and cover.endswith('(assets/01-cover.png)')
    images={}
    provenance={'images':json.loads((Path(__file__).parent/'artifact-QA.json').read_text())['figures']}
    for info in provenance['images']:
        path=PACK/info['file'];name=path.name;url=BASE+name
        expected=sha256(path.read_bytes()).hexdigest();assert expected==info['sha256']
        req=urllib.request.Request(url,headers={'User-Agent':'AICOM editorial image verification/1.0'})
        with urllib.request.urlopen(req,timeout=35) as response:
            assert response.status==200 and response.headers.get_content_type()=='image/png'
            content=response.read()
        assert sha256(content).hexdigest()==expected and content[:8]==b'\x89PNG\r\n\x1a\n'
        width,height=struct.unpack('>II',content[16:24])
        images[name]={'url':url,'sha256':expected,'width':width,'height':height}
        body=body.replace('(assets/'+name+')','('+url+')')
    assert len(images)==3 and len(re.findall(r'!\[',body))==2
    assert '(assets/' not in body and '/Users/' not in body and '<!-- DEMO_CODE -->' not in body
    assert len(fields['title'])<=128 and len(fields['description'])<=160
    tags=[t.strip() for t in fields['tags'].split(',')];assert len(tags)==4
    payload={'title':TITLE,'description':fields['description'],'tags':tags,'body_markdown':body,
             'main_image':images['01-cover.png']['url'],'ai_disclosure_level':'not_disclosed'}
    ready='\n'.join(['---','title: '+json.dumps(TITLE),'published: false',
                     'description: '+json.dumps(fields['description']),'tags: '+', '.join(tags),
                     'cover_image: '+payload['main_image'],'ai_disclosure_level: not_disclosed','---',''])+'\n'+body
    (PACK/'article.ready.md').write_text(ready)
    return payload,images,ready

def inspect(article,body,require_render=False):
    assert article.get('user',{}).get('username')=='alexar76'
    assert article['title']==TITLE and article['body_markdown']==body
    check=RenderCheck();check.feed(article.get('body_html') or '')
    if require_render:
        assert check.tables==1 and check.code==4
        assert len(check.images)==2 and all(i['alt'] and i['src'].startswith('https://') for i in check.images)
        assert all(link.startswith(('https://','#')) for link in check.links)
        assert 'MockLedger' in article['body_html'] and 'sameReplyDifferentBilling' in article['body_html']
        demo=(ROOT/'docs/evidence/devto-mcp-billing-2026-10-29/demo.py').read_text().strip()
        assert any(block.strip()==demo for block in check.code_text),'Rendered demonstration differs'
    return check

def main(action):
    assert api.request('/api/users/me')['username']=='alexar76','Wrong DEV account'
    payload,images,ready=prepared();body=payload['body_markdown'];digest=sha256(body.encode()).hexdigest()
    state=json.loads(STATE.read_text()) if STATE.exists() else {'author':'alexar76'}
    assert state['author']=='alexar76'
    if action=='draft':
        candidates=[]
        for page in range(1,11):
            batch=api.request(f'/api/articles/me/all?per_page=100&page={page}')
            candidates.extend(x for x in batch if x['title']==TITLE)
            if len(batch)<100:break
        else:raise RuntimeError('Author pagination exceeded limit')
        assert len(candidates)<=1,'Duplicate title'
        if candidates:
            article=api.get_article(candidates[0]['id']);inspect(article,body)
            assert not state.get('id') or state['id']==article['id']
        else:
            assert not state.get('id') and not state.get('pending'),'Reconcile previous write before creating'
            state.update(pending={'action':'create-draft','at':now(),'bodySha256':digest},images=images)
            save(state)
            article=api.request('/api/articles','POST',{'article':{**payload,'published':False}})
            inspect(article,body)
        state.update(id=article['id'],url=article['url'],images=images,bodySha256=digest,
                     draftCreatedOrRecoveredAt=now(),aiDisclosureLevel=article.get('ai_disclosure_level'))
        state.pop('pending',None);save(state)
        (PACK/'devto-draft-response.json').write_text(json.dumps(article,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'draft_verified':True,'id':article['id'],'url':article['url'],'rendered_html_present':bool(article.get('body_html'))}))
        return
    assert state.get('id') and not state.get('pending'),'Draft or reconciliation required'
    article=api.get_article(state['id'])
    if action=='update':
        assert article.get('user',{}).get('username')=='alexar76' and article['title']==TITLE
        assert article.get('published_at') and sha256(article['body_markdown'].encode()).hexdigest()==state['bodySha256']
        state['pending']={'action':'update-formatting','at':now(),'id':article['id'],'bodySha256':digest};save(state)
        article=api.request('/api/articles/'+str(article['id']),'PUT',{'article':{**payload,'published':True}})
        inspect(article,body)
        state.update(bodySha256=digest,formattingUpdatedAt=now());state.pop('pending',None);save(state)
    else:
        inspect(article,body)
    if action=='publish' and not article.get('published_at'):
        state['pending']={'action':'publish','at':now(),'id':article['id'],'bodySha256':digest};save(state)
        article=api.request('/api/articles/'+str(article['id']),'PUT',{'article':{**payload,'published':True}})
        inspect(article,body)
        assert article.get('published_at'),'Publication not confirmed'
        state.update(url=article['url'],publishedAt=article['published_at']);state.pop('pending',None);save(state)
    assert article.get('published_at'),'Article still unpublished'
    public=api.request('/api/articles'+article['path'],authenticated=False)
    check=inspect(public,body,require_render=True)
    assert public.get('published_at') and public.get('cover_image') and public.get('ai_disclosure_level')=='not_disclosed'
    (PACK/'devto-public.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    (PACK/'devto-rendered.html').write_text(public['body_html'])
    (PACK/'article.published.md').write_text(ready.replace('published: false','published: true',1))
    state.update(url=public['url'],publishedAt=public['published_at'],publiclyVerifiedAt=now(),
                 coverImage=public['cover_image'],inlineImages=check.images,renderedTables=check.tables,
                 renderedCodeBlocks=check.code,renderedDetails=check.details,
                 aiDisclosureLevel=public['ai_disclosure_level'],githubWrites=False)
    save(state)
    print(json.dumps({'published':True,'verified':True,'id':public['id'],'url':public['url'],'author':public['user']['username'],'inline_images':len(check.images),'cover':True,'code_blocks':check.code,'details':check.details}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('action',choices=['draft','publish','verify','update'])
    main(parser.parse_args().action)
