#!/usr/bin/env python3
"""Tell IndexNow which pages of our modelmarket.dev sites exist.

IndexNow reaches Bing (and through it DuckDuckGo, Yahoo, Ecosia), Yandex, Seznam, Naver and
Yep. On 2026-10-21 Bing had histor.modelmarket.dev and ecosystem.modelmarket.dev not at all,
while Google had both. Google does not take IndexNow; it reads the sitemaps.

The key is served by deploy/nginx/snippets/indexnow-key.conf on every host below; a host whose
key file does not answer is skipped. Standard library only, so it runs from the laptop or a host.

    python3 scripts/indexnow_submit.py                  # every site
    python3 scripts/indexnow_submit.py edu.modelmarket.dev --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_SNIPPET = Path(__file__).resolve().parents[1] / "deploy" / "nginx" / "snippets" / "indexnow-key.conf"
USER_AGENT = "modelmarket-indexnow/1.0"
BATCH = 10_000  # the protocol's limit per request

# Which sitemap lists each site's pages, pages no sitemap names yet, and the directory the key
# file sits in. HISTOR's own pages only: sitemap-0.xml names ~39k per-server pages, which Bing can
# crawl from the sitemap at its own pace; pushing them all at once would look like a flood.
# modelmarket.dev keeps its key in /blog/ (PromoMaterials/blog/build.py writes it), and IndexNow
# then takes only URLs under /blog/.
SITES = {
    "histor.modelmarket.dev": ("/sitemap-site.xml", ("/datasets/",), ""),
    "ecosystem.modelmarket.dev": ("/sitemap.xml", (), ""),
    "modeldev.modelmarket.dev": ("/sitemap.xml", (), ""),
    "edu.modelmarket.dev": ("/sitemap.xml", (), ""),
    "esim.modelmarket.dev": ("/sitemap.xml", (), ""),
    "modelmarket.dev": ("/blog/sitemap.xml", (), "/blog"),
}


def read_key(path: Path = KEY_SNIPPET) -> str:
    match = re.search(r"location = /([0-9a-f]{32})\.txt", path.read_text())
    if not match:
        raise SystemExit(f"no IndexNow key in {path}")
    return match.group(1)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, ""


def sitemap_urls(xml: str, host: str) -> list[str]:
    """Every <loc> and hreflang alternate on ``host``, in order, without repeats.

    A sitemap index is not followed: each site above names the one sitemap to read.
    """
    found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    found += re.findall(r"<xhtml:link[^>]*href=\"([^\"]+)\"", xml)
    out: list[str] = []
    for url in found:
        url = url.replace("&amp;", "&")
        if urlparse(url).hostname == host and url not in out:
            out.append(url)
    return out


def key_location(host: str, key: str, key_dir: str = "") -> str:
    return f"https://{host}{key_dir}/{key}.txt"


def key_served(host: str, key: str, key_dir: str = "") -> bool:
    status, body = fetch(key_location(host, key, key_dir))
    return status == 200 and body.strip() == key


def submit(host: str, key: str, urls: list[str], dry_run: bool, key_dir: str = "") -> bool:
    ok = True
    for start in range(0, len(urls), BATCH):
        batch = urls[start:start + BATCH]
        if dry_run:
            print(f"{host}: would send {len(batch)} URLs, e.g. {batch[:3]}")
            continue
        body = json.dumps({
            "host": host, "key": key, "keyLocation": key_location(host, key, key_dir), "urlList": batch,
        }).encode()
        req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
            "Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
        except urllib.error.HTTPError as err:
            status = err.code
        # 200 and 202 both mean received; 403 = key not matched, 422 = URL not on the host.
        print(f"{host}: {len(batch)} URLs → HTTP {status}")
        ok = ok and status in (200, 202)
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("hosts", nargs="*", help="sites to submit (default: all of SITES)")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent")
    args = parser.parse_args(argv)
    unknown = [h for h in args.hosts if h not in SITES]
    if unknown:
        parser.error(f"unknown site(s): {', '.join(unknown)}; known: {', '.join(SITES)}")
    key = read_key()
    failed = []
    for host in args.hosts or list(SITES):
        sitemap, extra, key_dir = SITES[host]
        if not key_served(host, key, key_dir):
            print(f"{host}: key file not served at {key_location(host, key, key_dir)} — skipped")
            failed.append(host)
            continue
        status, xml = fetch(f"https://{host}{sitemap}")
        urls = sitemap_urls(xml, host) if status == 200 else []
        urls += [u for u in (f"https://{host}{p}" for p in extra) if u not in urls]
        urls = [u for u in urls if u.startswith(f"https://{host}{key_dir}/")]
        if status != 200:
            print(f"{host}: sitemap {sitemap} answered HTTP {status}; sending only {len(urls)} listed pages")
        if not (urls and submit(host, key, urls, args.dry_run, key_dir)):
            failed.append(host)
    if failed:
        print(f"not submitted: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
