"""Verify local evidence integrity and a narrow public-value cross-check."""
from pathlib import Path
from collections import Counter
import hashlib,json
ROOT=Path(__file__).parent
rows=[]
for name in ['http-index.json','followup-index.json','final-reads-index.json','crawlcheck-reads-index.json','commit-index.json']:
    rows.extend(json.loads((ROOT/name).read_text()))
for row in rows:
    assert row.get('file'),row
    data=(ROOT/row['file']).read_bytes()
    assert len(data)==row['bytes'],row['key']
    assert hashlib.sha256(data).hexdigest()==row['sha256'],row['key']
current=json.loads((ROOT/'crawlcheck-vectors.raw').read_text())
pinned=json.loads((ROOT/'crawlcheck-pinned-vectors.raw').read_text())
assert current==pinned
record=json.loads((ROOT/'histor-crawlcheck-record.raw').read_text())['servers'][0]
fixture=pinned['baseline_cases'][0]['lock']['jcs_v1']['extras_sha256']
assert record['name']=='io.github.emmanuelorta/crawlcheck'
assert fixture==record['toolExtrasDigest']
out={
  'captures':len(rows),'unique_urls':len({r['url'] for r in rows}),
  'statuses':dict(Counter(str(r.get('status')) for r in rows)),
  'hashes_verified':len(rows),
  'crawlcheck_one_record_check':{
    'fixture_commit':'c634f497bd5873c2b2bd9f3ca9a26b188e08ac2a',
    'fixture_path':'sdk/test/fixtures/continuity.json',
    'fixture_json_path':'baseline_cases[0].lock.jcs_v1.extras_sha256',
    'histor_record':record['name'],'histor_last_observed':record['lastObserved'],
    'matching_extras_digest':fixture,
    'scope':'One published fixture versus one current HISTOR record; neither signature validation nor a new 30-server experiment.'
  }
}
(ROOT/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
