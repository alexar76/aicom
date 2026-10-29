#!/usr/bin/env python3
"""Check generated pages, local assets, anchors, translations, and published URLs."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from build import CONTENT, LANGUAGES, PROJECTS, ROOT, ASSET_PREFIX, render

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.ids=[]; self.links=[]; self.h1=0; self.lang=None
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag=='h1': self.h1+=1
        if tag=='html': self.lang=a.get('lang')
        for k in ['href','src']:
            if k in a: self.links.append(a[k])

for locale in LANGUAGES:
    copy=CONTENT[locale]
    assert copy.keys()==CONTENT['en'].keys(), locale
    # One description per project in every language: a project added to build.py needs its line here too.
    assert len(copy['descriptions'])==len(PROJECTS) and len(copy['filters'])==5, locale
    path=ROOT/('index.html' if locale=='en' else f'{locale}/index.html')
    source=path.read_text()
    assert source==render(locale,copy), f'Rebuild {locale}'
    page=Page(source)
    assert page.lang==locale and page.h1==1
    assert len(page.ids)==len(set(page.ids)), 'Duplicate anchor'
    assert 'http-equiv="refresh"' not in source and 'aicom.ai' not in source
    for link in page.links:
        if link.startswith('#'): assert link[1:] in page.ids, link
        elif link.startswith('/'):
            target=ROOT/urlsplit(link).path.lstrip('/')
            if link.endswith('/'): target=target/'index.html'
            assert target.is_file(), (locale,link)
    assert source.count('hreflang=')==11
font_root=ROOT/ASSET_PREFIX.lstrip('/')/'fonts'
css=(font_root/'fonts.css').read_text()
for url in re.findall(r'url\([\'\"]?([^\)\'\"]+)',css):
    assert (font_root/url).is_file(), url
print('PASS: 5 languages; generated content, anchors, local assets, font files, metadata, and project counts.')

# The maintained guides are served locally rather than depending on a GitHub publish.
for locale in LANGUAGES:
    name='knowledge-base'+('' if locale=='en' else '-'+locale)
    for relative in (f'docs/ecosystem/{name}.html', f'docs/ecosystem/whitepaper/{locale}.html'):
        path=ROOT/relative
        source=path.read_text()
        page=Page(source)
        assert page.lang==locale and page.h1==1, relative
        assert len(page.ids)==len(set(page.ids)), relative
        assert path.with_suffix('.md').is_file(), relative
        assert 'https://symmartys.modelmarket.dev/' in source, relative
        for link in page.links:
            if not link.startswith('/'): continue
            parsed=urlsplit(link)
            target=ROOT/parsed.path.lstrip('/')
            if parsed.path.endswith('/'): target=target/'index.html'
            assert target.is_file(), (relative,link)
            if parsed.fragment and target.suffix=='.html':
                assert unquote(parsed.fragment) in Page(target.read_text()).ids, (relative,link)
print('PASS: 10 hosted guides; local navigation, Markdown downloads, images, anchors and SYMMARTYS links.')
