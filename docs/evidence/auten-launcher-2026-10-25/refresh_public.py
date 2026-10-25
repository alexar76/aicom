#!/usr/bin/env python3
"""Read-only public evidence refresh; no account, execution or publication."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parent
URLS = {
    'census-comments': 'https://dev.to/api/comments?a_id=4847905',
    'comparison-comments': 'https://dev.to/api/comments?a_id=4868973',
    'auten-declaration': 'https://auten.ai/.well-known/mcp-tool-sets.json',
    'auten-package': 'https://registry.npmjs.org/@autenai%2Fmcp/latest',
    'warden-package': 'https://registry.npmjs.org/@aimarket%2Fwarden/0.21.0',
    'registry-entry': 'https://registry.modelcontextprotocol.io/v0.1/servers/ai.auten%2Fmcp/versions/latest',
    'histor-server': 'https://histor.modelmarket.dev/api/v1/servers/28f2c83985927b54',
}


def get(pair):
    name, url = pair
    item = {'name': name, 'url': url, 'checkedAt': datetime.now(timezone.utc).isoformat()}
    try:
        try:
            response = urlopen(Request(url, headers={'User-Agent': 'HISTOR-public-evidence-check/1.0'}), timeout=30)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(12 * 1024 * 1024 + 1)
            assert len(body) <= 12 * 1024 * 1024
            item.update({'status': response.status, 'sha256': sha256(body).hexdigest(), 'bytes': len(body)})
            (HERE / 'public' / (name + '.json')).write_bytes(body)
            if name in ('auten-package', 'warden-package') and response.status == 200:
                package = json.loads(body)
                item.update({'packageName': package['name'], 'version': package['version'],
                             'bin': package.get('bin'), 'dist': package.get('dist')})
    except Exception as exc:
        item['error'] = str(exc)
    return item


def main():
    (HERE / 'public').mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        result = list(pool.map(get, URLS.items()))
    (HERE / 'public-refresh.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
