#!/usr/bin/env python3
"""Unauthenticated GET of example links; never posts or modifies a service."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
IDS = (13185, 15587, 8738, 369, 3336)
FROZEN = {row['id']: row for row in (json.loads(line) for line in (HERE / 'transitions.jsonl').open())
          if row['id'] in IDS}


def check(change_id):
    url = f'https://histor.modelmarket.dev/api/v1/changes/{change_id}'
    record = {'id': change_id, 'url': url}
    try:
        with urlopen(Request(url, headers={'User-Agent': 'HISTOR-public-evidence-check/1.0'}), timeout=30) as response:
            body = response.read()
            value = json.loads(body)
            record.update({'httpStatus': response.status, 'returnedId': value.get('id'),
                           'keys': sorted(value), 'sha256': hashlib.sha256(body).hexdigest()})
            assert value.get('id') == change_id
            expected = FROZEN[change_id]
            record['matchesFrozenTransition'] = all(value[a] == expected[b] for a, b in (
                ('from_toolset', 'fromToolSetDigest'), ('to_toolset', 'toToolSetDigest'),
                ('observed_at', 'observedAt')))
            assert record['matchesFrozenTransition']
            (HERE / 'public-examples' / f'{change_id}.json').write_bytes(body)
    except Exception as exc:
        record['error'] = str(exc)
    return record


def main():
    (HERE / 'public-examples').mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(check, IDS))
    result = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'authentication': 'none', 'method': 'GET',
              'results': results}
    (HERE / 'public-links.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
