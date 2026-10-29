"""Public registry/dependency metadata only. Never download or execute packages."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
PACKAGES = ['aimarket-metis', 'aimarket-logos', 'aimarket-oracle-core', 'aimarket-hestia', 'helios-broadcast', 'skopos-fleet', 'aimarket-emporion', 'aimarket-basanos', 'aimarket-dolos', 'aimarket-themis']

def get(url):
    row = {'url': url, 'method': 'GET', 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 public metadata research'}), timeout=25) as response:
            raw = response.read()
            row.update(status=response.status, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        return row, json.loads(raw)
    except urllib.error.HTTPError as error:
        row.update(status=error.code, error=str(error))
    except Exception as error:
        row.update(status=None, error=str(error))
    return row, None

def metadata(name):
    request, data = get('https://pypi.org/pypi/' + urllib.parse.quote(name, safe='') + '/json')
    out = {'name': name, 'request': request}
    if not data:
        return out
    info = data.get('info', {})
    out['metadata'] = {key: info.get(key) for key in ['name', 'version', 'project_urls', 'home_page', 'requires_dist']}
    urls = json.dumps([info.get('project_urls'), info.get('home_page')])
    out['attributed_to_ecosystem'] = 'github.com/alexar76/' in urls or 'modelmarket.dev' in urls
    released = []
    for version, files in data.get('releases', {}).items():
        times = [file.get('upload_time_iso_8601') for file in files if file.get('upload_time_iso_8601')]
        if times:
            released.append((min(times), version))
    released.sort()
    selected = []
    if released:
        selected.append({'version': released[0][1], 'selection': 'earliest release with a file', 'first_upload': released[0][0]})
    latest = info.get('version')
    if latest and latest not in [row['version'] for row in selected]:
        selected.append({'version': latest, 'selection': 'current PyPI version', 'first_upload': next((date for date, version in released if version == latest), None)})
    out['selected_versions'] = selected
    return out

def dependents(task):
    name, version = task
    url = 'https://deps.dev/_/s/pypi/p/' + urllib.parse.quote(name, safe='') + '/v/' + urllib.parse.quote(version, safe='') + '/dependents'
    request, data = get(url)
    return {'name': name, 'version': version, 'request': request, 'result': data}

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(metadata, PACKAGES))
    (ROOT/'reverse-package-scope.json').write_text(json.dumps(packages, ensure_ascii=False, indent=2)+'\n')
    tasks = [(row['name'], version['version']) for row in packages if row.get('attributed_to_ecosystem') for version in row.get('selected_versions', [])]
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(dependents, tasks))
    (ROOT/'reverse-dependent-results.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'package_scope': [{'name': row['name'], 'status': row['request']['status'], 'attributed': row.get('attributed_to_ecosystem'), 'versions': row.get('selected_versions')} for row in packages], 'dependents': [{'name': row['name'], 'version': row['version'], 'status': row['request']['status'], 'total': (row['result'] or {}).get('totalCount'), 'directSample': (row['result'] or {}).get('directSample')} for row in records]}, ensure_ascii=False))
