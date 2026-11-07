"""Fetch whole public databases; no source or inventory leaves the workspace."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

OUT = Path(__file__).resolve().parent
CACHE = Path('/private/tmp/aicom-security-audit-20261107')


def fetch(ecosystem):
    url = f'https://osv-vulnerabilities.storage.googleapis.com/{ecosystem}/all.zip'
    request = urllib.request.Request(url, headers={'User-Agent': 'aicom-local-audit'})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
        headers = {key: response.headers.get(key) for key in ('ETag', 'Last-Modified')}
    CACHE.mkdir(exist_ok=True)
    destination = CACHE / f'{ecosystem}.zip'
    destination.write_bytes(body)
    result = dict(ecosystem=ecosystem, url=url, path=str(destination), bytes=len(body),
                  sha256=hashlib.sha256(body).hexdigest(), headers=headers,
                  fetched_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    print(ecosystem, len(body), flush=True)
    return result


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, ('npm', 'crates.io', 'Go', 'Pub')))
    (OUT / 'osv-download-provenance.json').write_text(json.dumps(rows, indent=2) + '\n')
