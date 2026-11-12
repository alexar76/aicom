"""Acquire only metadata-declared public covers into the isolated setup cache."""
from __future__ import annotations

import concurrent.futures
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import urllib.parse
import urllib.request

ROOT = Path('/input/aicom/modelmarket-blog')
CACHE = Path('/cache')
LIMIT = 16 * 1024 * 1024
FONTS = (
    'orbitron-yMJRMIlzdpvBhQQL_Qq7dy1biN15.woff2',
    'rajdhani-LDI2apCSOBg7S-QT7pa8FvOreefkkbIx.woff2',
)


def public_https(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    assert parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
    addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    assert addresses and all(ipaddress.ip_address(address).is_global for address in addresses), 'Cover URL is not public'


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def cover(meta_path: Path) -> dict | None:
    meta = json.loads(meta_path.read_text())
    if meta.get('draft') or meta.get('cover_file') or not meta.get('cover_image'):
        return None
    url = meta['cover_image']
    match = re.search(r'/(https?%3A%2F%2F[^/?#]+)$', url)
    if match:
        url = urllib.parse.unquote(match.group(1))
    public_https(url)
    extension = Path(urllib.parse.urlparse(url).path).suffix.lower() or '.img'
    relative = Path('cache/covers') / (meta_path.parent.name + extension)
    destination = CACHE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'modelmarket-blog-build/1.0 (+https://modelmarket.dev/blog/)'})
    with urllib.request.build_opener(PublicRedirects()).open(request, timeout=45) as response:
        raw = response.read(LIMIT + 1)
    assert 0 < len(raw) <= LIMIT, 'Public cover is empty or exceeds the acquisition bound'
    destination.write_bytes(raw)
    return {'cache_path': str(relative), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'source_meta': str(meta_path.relative_to(ROOT)), 'source_url_sha256': hashlib.sha256(url.encode()).hexdigest()}


CACHE.mkdir(parents=True, exist_ok=True)
files = []
for filename in FONTS:
    source = Path('/input/aicom/aimarket-hub/aimarket_hub/assets/fonts') / filename
    relative = Path('cache/fonts') / filename
    destination = CACHE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    files.append({'cache_path': str(relative), 'bytes': source.stat().st_size, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'source_git_path': 'aimarket-hub/aimarket_hub/assets/fonts/' + filename})
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    files.extend(entry for entry in pool.map(cover, sorted((ROOT / 'posts').glob('*/meta.json'))) if entry is not None)
manifest = {'scope': 'Git public fonts and metadata-declared public HTTPS covers only; no credentials', 'files': sorted(files, key=lambda entry: entry['cache_path'])}
(CACHE / 'cache-provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'public_cache_files': len(files)}))
