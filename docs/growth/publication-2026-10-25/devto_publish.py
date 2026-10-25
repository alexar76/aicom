"""Publish only the three reviewed articles, with identity and duplicate checks.

User explicitly authorized DEV articles and Martin/jkming replies on 2026-10-25.
This script never sends replies and never calls GitHub. Keys are never logged.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
ENV = Path('/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/devto/.env')
STATE = ROOT / 'devto-state.json'
TOPICS = ('kartik', 'jkming', 'martin')


def load_key():
    for raw in ENV.read_text().splitlines():
        if raw.strip().startswith('DEVTO_API_KEY='):
            key = raw.split('=', 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError('DEV key unavailable')


KEY = load_key()


def request(path, method='GET', payload=None, authenticated=True):
    assert path.startswith('/api/')
    headers = {'Accept': 'application/vnd.forem.api-v1+json', 'User-Agent': 'AICOM editorial/1.0'}
    if authenticated:
        headers['api-key'] = KEY
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request('https://dev.to' + path, method=method, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)


def now():
    return datetime.now(timezone.utc).isoformat()


def save(state):
    tmp = STATE.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(STATE)


def parse(topic):
    text = (ROOT / topic / 'article.md').read_text()
    assert text.startswith('---\n')
    _, front, body = text.split('---', 2)
    fields = dict(line.split(':', 1) for line in front.strip().splitlines())
    fields = {k.strip(): v.strip().strip('"') for k, v in fields.items()}
    body = body.lstrip('\n')
    assert 'ARTICLE_URL' not in body and '/Users/' not in body and '../' not in body
    assert not re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', body)
    assert re.search(r'disclosure.*Fully Autonomous', body, re.I) and 'AI agents prepared' in body
    tags = [t.strip() for t in fields['tags'].split(',')]
    assert len(tags) <= 4 and len(fields['title']) <= 128
    return {'title': fields['title'], 'body_markdown': body, 'tags': tags, 'ai_disclosure_level': 'fully_autonomous',
            'description': fields.get('description', '')[:160]}


class RenderCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'table':
            self.tables += 1
        if tag == 'a' and 'href' in values:
            self.links.append(values['href'])


def get_article(article_id):
    try:
        return request(f'/api/articles/{article_id}')
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    matches = [a for a in request('/api/articles/me/all?per_page=100') if a['id'] == article_id]
    assert len(matches) == 1, 'Article unavailable in public and author lists'
    found = matches[0]
    if found.get('published_at'):
        return request('/api/articles' + found['path'], authenticated=False)
    return found


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=('draft', 'publish', 'verify'))
    args = parser.parse_args()
    me = request('/api/users/me')
    assert me.get('username') == 'alexar76', 'Unexpected author identity'
    state = json.loads(STATE.read_text()) if STATE.exists() else {'author': 'alexar76', 'articles': {}}
    assert state['author'] == 'alexar76'
    existing = request('/api/articles/me/all?per_page=100')
    for topic in TOPICS:
        article = parse(topic)
        body_hash = sha256(article['body_markdown'].encode()).hexdigest()
        entry = state['articles'].get(topic)
        if args.action == 'draft' and entry is None:
            matches = [x for x in existing if x['title'] == article['title']]
            assert len(matches) <= 1, 'Ambiguous duplicate title'
            if matches:
                found = get_article(matches[0]['id'])
                assert found['body_markdown'] == article['body_markdown'], 'Existing title differs'
                entry = {'id': found['id'], 'url': found['url'], 'recoveredExisting': True}
            else:
                state['pending'] = {'topic': topic, 'bodySha256': body_hash, 'at': now()}
                save(state)
                found = request('/api/articles', 'POST', {'article': {**article, 'published': False}})
                assert found.get('user', {}).get('username') == 'alexar76'
                entry = {'id': found['id'], 'url': found['url'], 'createdAt': now()}
            state['articles'][topic] = entry
            state.pop('pending', None)
            save(state)
        assert entry is not None, f'Create reviewed draft first: {topic}'
        if args.action == 'draft':
            found = get_article(entry['id'])
            assert found.get('user', {}).get('username') == 'alexar76' and found['title'] == article['title']
            if found['body_markdown'] != article['body_markdown']:
                assert entry.get('createdAt'), 'Only update drafts created by this recorded publication run'
                assert not found.get('published_at'), 'Draft review must not silently edit a published article'
                found = request(f"/api/articles/{entry['id']}", 'PUT', {'article': {**article, 'published': False}})
        if args.action == 'publish':
            found = get_article(entry['id'])
            assert found.get('user', {}).get('username') == 'alexar76'
            assert found['body_markdown'] == article['body_markdown'], 'Draft changed after review'
            if not found.get('published_at'):
                found = request(f"/api/articles/{entry['id']}", 'PUT', {'article': {**article, 'published': True}})
            assert found.get('published_at'), 'Publication not confirmed'
            entry.update({'url': found['url'], 'publishedAt': found['published_at']})
            save(state)
        # An authenticated fetch verifies drafts; a second unauthenticated fetch verifies publication.
        found = get_article(entry['id'])
        assert found.get('user', {}).get('username') == 'alexar76'
        assert found['body_markdown'] == article['body_markdown']
        html = found.get('body_html', '')
        check = RenderCheck()
        check.feed(html)
        if html:
            assert check.tables >= 1 and 'ARTICLE_URL' not in html and 'Fully Autonomous' in html
        else:
            assert re.search(r'^\|\s*-', article['body_markdown'], re.M), 'No Markdown table'
        assert all(href.startswith(('https://', '#')) for href in check.links), check.links
        if found.get('published_at'):
            public = request('/api/articles' + found['path'], authenticated=False)
            assert public.get('user', {}).get('username') == 'alexar76' and public.get('published_at')
            assert public['body_markdown'] == article['body_markdown']
            assert public.get('ai_disclosure_level') == 'fully_autonomous'
        entry.update({'url': found['url'], 'bodySha256': body_hash, 'publishedAt': found.get('published_at'),
                      'verifiedAt': now(), 'renderedTables': check.tables if html else None,
                      'renderedLinks': len(check.links) if html else None,
                      'aiDisclosureLevelRequested': 'fully_autonomous',
                      'aiDisclosureLevelVerified': found.get('ai_disclosure_level')})
        (ROOT / topic / 'devto-rendered.html').write_text(html)
        (ROOT / topic / 'article.published.md').write_text((ROOT / topic / 'article.md').read_text().replace('published: false', 'published: true', 1) if found.get('published_at') else (ROOT / topic / 'article.md').read_text())
        save(state)
        print(json.dumps({'topic': topic, **entry}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
