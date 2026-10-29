"""Publish the explicitly authorized, illustrated Launch Gate article as alexar76.

No comments, messages, unrelated article edits, npm or GitHub writes.
Writes are never retried automatically after an uncertain response.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
STATE = HERE / 'devto-publication.json'
SLUG = 'we-improved-wardens-warnings-twelve-rechecks-changed-no-choices'
BLOG_URL = 'https://modelmarket.dev/blog/' + SLUG + '/'


def save(value):
    temporary = STATE.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(STATE)


class RenderCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = 0
        self.images = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'table':
            self.tables += 1
        if tag == 'img':
            self.images.append(values.get('src', ''))
        if tag == 'a':
            self.links.append(values.get('href', ''))


def main():
    spec = importlib.util.spec_from_file_location('existing_devto_client', HERE.parent / 'devto_publish.py')
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)  # Loads the existing credential without printing it.
    assert api.request('/api/users/me')['username'] == 'alexar76', 'Unexpected author'
    text = (HERE / 'article.ready.md').read_text()
    _, front, body = text.split('---', 2)
    fields = {key.strip(): value.strip().strip('"') for key, value in (line.split(':', 1) for line in front.strip().splitlines())}
    body = body.lstrip('\n')
    assert fields['canonical_url'] == BLOG_URL and fields['main_image'] == BLOG_URL + 'cover.webp'
    assert '../../' not in body and '/Users/' not in body and 'AI assistance' in body
    assert len(re.findall(r'!\[', body)) >= 1
    links = set(re.findall(r'\]\((https://[^)]+)\)', body)) | {fields['canonical_url'], fields['main_image']}
    for link in links:
        # Public evidence and image URLs must be live before DEV receives them.
        if not link.startswith(BLOG_URL):
            continue
        request = urllib.request.Request(link, method='HEAD', headers={'User-Agent': 'AICOM publication verification/1.0'})
        with urllib.request.urlopen(request, timeout=35) as response:
            assert response.status == 200, link
    payload = {'title': fields['title'], 'description': fields['description'], 'tags': [tag.strip() for tag in fields['tags'].split(',')], 'body_markdown': body, 'main_image': fields['main_image'], 'canonical_url': BLOG_URL, 'ai_disclosure_level': 'not_disclosed'}
    digest = sha256(body.encode()).hexdigest()
    state = json.loads(STATE.read_text()) if STATE.exists() else {'author': 'alexar76', 'blogUrl': BLOG_URL}
    assert state['author'] == 'alexar76' and state['blogUrl'] == BLOG_URL
    existing = api.request('/api/articles/me/all?per_page=100')
    matches = [article for article in existing if article['title'] == fields['title']]
    assert len(matches) <= 1, 'Duplicate article title'
    if matches:
        article = api.get_article(matches[0]['id'])
        assert article.get('body_markdown') == body, 'Matching title has different or unavailable content'
        if state.get('id'):
            assert state['id'] == article['id']
    else:
        assert not state.get('id'), 'Recorded article missing; do not create a duplicate'
        assert not state.get('pending'), 'Uncertain earlier create; reconcile manually instead of retrying'
        state.update(pending={'action': 'create-draft', 'bodySha256': digest, 'at': datetime.now(timezone.utc).isoformat()})
        save(state)
        article = api.request('/api/articles', 'POST', {'article': {**payload, 'published': False}})
        assert article['user']['username'] == 'alexar76' and article['body_markdown'] == body
    state.update(id=article['id'], url=article['url'], bodySha256=digest, canonicalUrl=BLOG_URL)
    state.pop('pending', None)
    save(state)
    if not article.get('published_at'):
        state['pending'] = {'action': 'publish', 'id': article['id'], 'bodySha256': digest, 'at': datetime.now(timezone.utc).isoformat()}
        save(state)
        article = api.request('/api/articles/' + str(article['id']), 'PUT', {'article': {**payload, 'published': True}})
    assert article['published_at'] and article['user']['username'] == 'alexar76'
    state.update(url=article['url'], publishedAt=article['published_at'])
    state.pop('pending', None)
    save(state)
    public = api.request('/api/articles' + article['path'], authenticated=False)
    assert public['user']['username'] == 'alexar76' and public['published_at']
    assert public['body_markdown'] == body and public['canonical_url'].rstrip('/') == BLOG_URL.rstrip('/')
    assert public.get('cover_image') and public.get('ai_disclosure_level') == 'not_disclosed'
    check = RenderCheck()
    check.feed(public['body_html'])
    assert check.tables >= 1 and check.images, 'Missing table or inline graph'
    assert all(link.startswith(('https://', '#')) for link in check.links), 'Non-public link in published article'
    (HERE / 'devto-public.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'devto-rendered.html').write_text(public['body_html'])
    (HERE / 'article.published.md').write_text(text.replace('published: false', 'published: true', 1))
    state.update(publiclyVerifiedAt=datetime.now(timezone.utc).isoformat(), tables=check.tables, inlineImages=len(check.images), coverImage=public['cover_image'], detailedAiDisclosureRetained=True, aiBadge='not_disclosed', githubWrites=False, npmPublished=False)
    save(state)
    print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    main()
