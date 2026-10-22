"""scripts/indexnow_submit.py: the key it sends is the one nginx serves, on every site it names.

A site whose vhost does not include the key snippet answers the key URL with its own page,
and IndexNow then refuses every URL for that host (HTTP 403).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("indexnow_submit", ROOT / "scripts" / "indexnow_submit.py")
indexnow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(indexnow)

VHOSTS = {
    "histor.modelmarket.dev": ROOT / "histor" / "deploy" / "nginx" / "histor.modelmarket.dev.conf",
    "ecosystem.modelmarket.dev": ROOT / "deploy" / "nginx" / "ecosystem.modelmarket.dev.conf",
    "modeldev.modelmarket.dev": ROOT / "deploy" / "nginx" / "modeldev.modelmarket.dev.conf",
    "edu.modelmarket.dev": ROOT / "deploy" / "nginx" / "edu.modelmarket.dev.conf",
    "esim.modelmarket.dev": ROOT / "deploy" / "nginx" / "esim.modelmarket.dev.conf",
}


def test_the_key_is_read_from_the_snippet_nginx_serves():
    key = indexnow.read_key()
    snippet = indexnow.KEY_SNIPPET.read_text()
    assert len(key) == 32
    assert f'return 200 "{key}";' in snippet


def test_every_site_includes_the_key_snippet():
    at_root = {h for h, (_s, _e, key_dir) in indexnow.SITES.items() if not key_dir}
    assert at_root == set(VHOSTS)
    for host, conf in VHOSTS.items():
        assert "include /etc/nginx/snippets/indexnow-key.conf;" in conf.read_text(), host


def test_a_key_in_a_directory_only_vouches_for_that_directory():
    sitemap, _extra, key_dir = indexnow.SITES["modelmarket.dev"]
    assert key_dir == "/blog" and sitemap.startswith("/blog/")
    assert indexnow.key_location("modelmarket.dev", "k" * 32, key_dir) == f"https://modelmarket.dev/blog/{'k' * 32}.txt"


def test_sitemap_urls_keep_this_host_and_its_language_versions():
    xml = """<urlset xmlns:xhtml="http://www.w3.org/1999/xhtml">
      <url><loc>https://edu.modelmarket.dev/</loc>
        <xhtml:link rel="alternate" hreflang="ru" href="https://edu.modelmarket.dev/?lang=ru&amp;x=1"/>
        <xhtml:link rel="alternate" hreflang="en" href="https://edu.modelmarket.dev/"/></url>
      <url><loc> https://edu.modelmarket.dev/a </loc></url>
      <url><loc>https://modeldev.modelmarket.dev/learn/</loc></url>
    </urlset>"""
    assert indexnow.sitemap_urls(xml, "edu.modelmarket.dev") == [
        "https://edu.modelmarket.dev/",
        "https://edu.modelmarket.dev/a",
        "https://edu.modelmarket.dev/?lang=ru&x=1",
    ]


def test_unknown_sites_are_refused():
    try:
        indexnow.main(["example.com", "--dry-run"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("an unknown host must be refused before anything is fetched")
