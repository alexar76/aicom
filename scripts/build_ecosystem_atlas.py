#!/usr/bin/env python3
"""Overlay the standalone atlas while preserving existing ecosystem/SEO content."""
import argparse
import importlib.util
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path, base_url: str) -> None:
    source = ROOT / 'scripts/github-io'
    os.environ['ATLAS_SITE_URL'] = base_url.rstrip('/')
    os.environ['ATLAS_ASSET_PREFIX'] = '/ecosystem-atlas'
    spec = importlib.util.spec_from_file_location('ecosystem_atlas', source / 'build.py')
    atlas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(atlas)
    output.mkdir(parents=True, exist_ok=True)
    for locale, copy in atlas.CONTENT.items():
        destination = output / ('' if locale == 'en' else locale)
        destination.mkdir(exist_ok=True)
        (destination / 'index.html').write_text(atlas.render(locale, copy))
    for folder in ['assets', 'fonts']:
        shutil.copytree(source / folder, output / 'ecosystem-atlas' / folder, dirs_exist_ok=True)
    # Keep encyclopedia, courses and all other existing sitemap entries.
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    sitemap = output / 'sitemap.xml'
    if sitemap.exists():
        tree = ET.parse(sitemap)
        if tree.getroot().tag != f'{{{namespace}}}urlset':
            raise ValueError('Expected a urlset; refusing to replace an unknown sitemap format')
    else:
        tree = ET.ElementTree(ET.Element(f'{{{namespace}}}urlset'))
    urls = {node.text for node in tree.findall(f'.//{{{namespace}}}loc')}
    for locale in atlas.LANGUAGES:
        url = base_url.rstrip('/') + atlas.route(locale)
        if url not in urls:
            entry = ET.SubElement(tree.getroot(), f'{{{namespace}}}url')
            ET.SubElement(entry, f'{{{namespace}}}loc').text = url
    tree.write(sitemap, encoding='utf-8', xml_declaration=True)
    if not (output / 'robots.txt').exists():
        (output / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {base_url.rstrip("/")}/sitemap.xml\n')
    print(f'Atlas: {output}; preserved existing sections and sitemap entries.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'ecosystem-landing')
    parser.add_argument('--base-url', default='https://ecosystem.modelmarket.dev')
    args = parser.parse_args()
    build(args.output, args.base_url)
