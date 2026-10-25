#!/usr/bin/env python3
"""Fetch public immutable evidence; all network calls are unauthenticated GETs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / 'histor'), str(ROOT / 'awr/reference/python')]
from histor.subject import tool_set_digest
from awr import canonical_sri

ORIGIN = 'https://histor.modelmarket.dev'
IDS = (17172, 20433, 23671)

def get(item):
    path, url = item
    request = urllib.request.Request(url, headers={'User-Agent': 'HISTOR-public-evidence-review/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read()
        status = response.status
        final_url = response.url
    json.loads(body)
    path.write_bytes(body)
    return {'file': str(path.relative_to(HERE)), 'url': url, 'finalURL': final_url,
            'status': status, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}

def main():
    candidates=json.loads((HERE/'candidates.json').read_text())['candidates']
    by_id={c['change']['id']: c for c in candidates}
    jobs=[]
    for event_id in IDS:
        c=by_id[event_id]
        out=HERE/'real-cases'/str(event_id)
        out.mkdir(parents=True, exist_ok=True)
        (out/'snapshot-metadata.json').write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
        jobs.extend([(out/'change.json',f'{ORIGIN}/api/v1/changes/{event_id}'),
                     (out/'server.json',f'{ORIGIN}/api/v1/servers/{c["server"]["id"]}')])
        for side in ('from','to'):
            for kind, key in [('toolsets','ToolSetDigest'),('descriptors','SubjectDigest')]:
                digest=c['change'][side+key]
                url=f'{ORIGIN}/api/v1/{kind}/{urllib.parse.quote(digest,safe="")} '
                jobs.append((out/f'{side}-{kind}.json',url.strip()))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(get,jobs))
    checks=[]
    for event_id in IDS:
        c=by_id[event_id]
        out=HERE/'real-cases'/str(event_id)
        change=json.loads((out/'change.json').read_bytes())
        assert change['id']==event_id and change['target_id']==c['server']['id']
        assert change['observed_at']==c['change']['observedAt']
        for api_key,frozen_key in [('from_toolset','fromToolSetDigest'),('to_toolset','toToolSetDigest'),
                                   ('from_subject','fromSubjectDigest'),('to_subject','toSubjectDigest')]:
            assert change[api_key]==c['change'][frozen_key]
        for side in ('from','to'):
            tools=json.loads((out/f'{side}-toolsets.json').read_bytes())
            observed, normalised = tool_set_digest(tools)
            expected=c['change'][side+'ToolSetDigest']
            assert observed==expected, (event_id,side,observed,expected)
            descriptor=json.loads((out/f'{side}-descriptors.json').read_bytes())
            assert canonical_sri(descriptor)==c['change'][side+'SubjectDigest']
            checks.append({'changeId':event_id,'side':side,'tools':len(tools),
                           'toolSetDigest':observed,'subjectDigest':canonical_sri(descriptor),
                           'artifact':descriptor.get('artifact')})
        before=json.loads((out/'from-toolsets.json').read_bytes())
        after=json.loads((out/'to-toolsets.json').read_bytes())
        # Human display only; raw canonical JSON remains alongside this diff.
        diff=''.join(difflib.unified_diff(
            json.dumps(before,ensure_ascii=False,indent=2,sort_keys=True).splitlines(True),
            json.dumps(after,ensure_ascii=False,indent=2,sort_keys=True).splitlines(True),
            fromfile='from-toolsets.json',tofile='to-toolsets.json'))
        (out/'toolsets.diff').write_text(diff)
    metadata={'fetchedAt':datetime.now(timezone.utc).isoformat(),
              'requests':results,'digestChecks':checks,
              'scope':'Public GET only; no external packages or MCP servers executed.'}
    (HERE/'real-cases'/'fetch-verification.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'files':len(results),'digestChecks':checks},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
