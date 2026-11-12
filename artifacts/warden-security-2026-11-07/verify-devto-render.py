"""Inspect the published rendering in a remote gVisor client, without API keys."""
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request


class Rendering(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []
        self.tables = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'img':
            self.images.append(attributes)
        elif tag == 'a' and attributes.get('href'):
            self.links.append(attributes['href'])
        elif tag == 'table':
            self.tables += 1


root = Path('/output')
article = json.loads((root / 'devto-public.json').read_text())
assert article['user']['username'] == 'alexar76'
assert article['ai_disclosure_level'] == 'not_disclosed'
assert article['published_at']
assert 'AI assistance was used' in article['body_markdown']
assert article['cover_image'].startswith('https://')
render = Rendering()
render.feed(article['body_html'])
assert render.tables == 3, render.tables
assert len(render.images) == 3, len(render.images)
assert all(image.get('alt') and image.get('src', '').startswith('https://')
           for image in render.images)
assert all(link.startswith(('https://', '#')) for link in render.links)
assert any(link.endswith('/reports-and-data.zip') for link in render.links)
request = urllib.request.Request(article['url'], headers={
    'User-Agent': 'Mozilla/5.0 (compatible; AIMarket-editorial-verification/1.0)',
    'Accept-Encoding': 'identity',
})
with urllib.request.urlopen(request, timeout=60) as response:
    assert response.status == 200
    page = response.read(4 * 1024 * 1024)
    assert article['title'].encode() in page
    public_page = {'url': response.url, 'status': response.status,
                   'httpDate': response.headers.get('Date'), 'bytes': len(page)}
receipt = {'format': 'warden.devto-render-verification/v1',
           'execution': 'remote gVisor', 'allPassed': True,
           'articleId': article['id'], 'tables': render.tables,
           'inlineImages': render.images, 'coverImage': article['cover_image'],
           'links': len(render.links), 'publicPage': public_page,
           'author': 'alexar76', 'aiDisclosureLevel': 'not_disclosed',
           'proseAiDisclosureRetained': True}
(root / 'devto-render-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
