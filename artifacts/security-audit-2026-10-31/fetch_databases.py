"""Download public advisory data only; never transmit source or credentials."""
import concurrent.futures
import datetime
import hashlib
import json
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
CACHE = Path('/private/tmp/aicom-security-audit-20261031')
CACHE.mkdir(exist_ok=True)


def fetch(url, dest):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'aicom-security-audit'})
            with urllib.request.urlopen(req, timeout=90) as response:
                data = response.read()
                modified = response.headers.get('Last-Modified')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {'url': url, 'path': str(dest), 'bytes': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(), 'last_modified': modified,
                    'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)


def main():
    provenance = []
    provenance.append(fetch('https://api.github.com/repos/Vulnetix/advisory-database/commits/main', OUT/'vulnetix-head.json'))
    sha = json.loads((OUT/'vulnetix-head.json').read_text())['sha']
    base = f'https://raw.githubusercontent.com/Vulnetix/advisory-database/{sha}/'
    requests = [(base+'index/manifest.json', CACHE/'vulnetix-manifest.json')]
    requests += [(f'https://osv-vulnerabilities.storage.googleapis.com/{eco}/all.zip', CACHE/(eco+'.zip')) for eco in ('npm', 'PyPI', 'crates.io', 'Go', 'Pub')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, *args) for args in requests]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            provenance.append(row)
            print('downloaded', Path(row['path']).name, row['bytes'], flush=True)
    (OUT/'download-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    families = {'PYPI','NPM','GO','CARGO','VULN-PYPI','VULN-NPM','VULN-GO','VULN-CARGO'}
    rows = json.loads((CACHE/'vulnetix-manifest.json').read_text())['records']
    selected = [r for r in rows if r['family'] in families and r['state'] == 'published']
    def get_record(row):
        result = fetch(base+row['paths']['osv'], CACHE/'vulnetix-osv'/(row['id']+'.json'))
        assert json.loads(Path(result['path']).read_text())['id'] == row['id']
        return {**result, 'id': row['id'], 'classification': row['classification']}
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for result in pool.map(get_record, selected):
            records.append(result)
            if len(records) % 200 == 0:
                print('Vulnetix records', len(records), '/', len(selected), flush=True)
    (OUT/'vulnetix-provenance.json').write_text(json.dumps({'commit': sha, 'records': records}, indent=2)+'\n')
    print('complete', len(records), 'Vulnetix records', flush=True)


if __name__ == '__main__':
    main()
