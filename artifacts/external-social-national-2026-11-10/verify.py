"""Verify this pass's saved evidence without making network requests."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
plans = {
    'root': ['http-index.json'],
    'regions': ['primary-index.json'],
    'east-asia': ['sources-01-index.json', 'sources-02-index.json', 'sources-03-index.json'],
    'social': ['native-initial-index.json', 'native-followup-index.json', 'native-new-article-index.json'],
}
errors, checks, branches = [], [], {}
for branch, names in plans.items():
    rows = []
    for name in names:
        rows.extend(json.loads((ROOT / branch / name).read_text()))
    for row in rows:
        file = row.get('body_file') or row.get('body_path') or row.get('file')
        if file is None:
            errors.append({'branch': branch, 'url': row.get('url'), 'reason': 'no_saved_body', 'error':row.get('error')})
            continue
        path = ROOT / branch / file
        data = path.read_bytes()
        complete = row.get('complete', not row.get('truncated', False))
        ok = len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'] and complete
        checks.append({'file': str(path.relative_to(ROOT)), 'status': row.get('status'),
                       'bytes':len(data), 'length_sha256_and_completeness_pass': ok})
        if not ok:
            errors.append({'file': str(path), 'reason': 'capture_integrity_failed'})
    branches[branch] = {'get_attempts': len(rows), 'http_statuses': dict(Counter(str(r.get('status','network_error')) for r in rows))}

json_files = list(ROOT.rglob('*.json'))
for path in json_files:
    try:
        json.loads(path.read_text())
    except Exception as exc:
        errors.append({'file':str(path), 'error':str(exc)})

local_links = []
for path in ROOT.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if link.startswith(('http://','https://','#','mailto:','codex:','plugin:')):
            continue
        target = link.strip('<>').split('#',1)[0]
        if not target:
            continue
        exists = (path.parent / target).exists()
        local_links.append({'from':str(path.relative_to(ROOT)), 'target': target, 'exists': exists})
        if not exists:
            errors.append({'from':str(path), 'target':target, 'reason':'missing_local_link'})

result = {'verified_at':datetime.now(timezone.utc).isoformat(),
          'branches': branches, 'get_attempts':sum(v['get_attempts'] for v in branches.values()),
          'saved_complete_bodies_verified':len(checks), 'json_files_parsed':len(json_files),
          'captures':checks, 'local_report_links':local_links, 'errors':errors,
          'all_passed':not errors,
          'note':'HTTP403/502 responses are complete evidence bodies, not successful reads of requested content. Search-engine tool captures are stored separately and not counted as direct GET attempts.'}
(ROOT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['captures','local_report_links']},ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
