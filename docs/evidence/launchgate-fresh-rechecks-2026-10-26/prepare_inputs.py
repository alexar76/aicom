"""Extract exact saved contexts; no model calls or test execution on the Mac."""
from hashlib import sha256
import json
from pathlib import Path
import re
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v): return sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()

def main():
    pairs=json.loads((HERE.parent/'launchgate-reason-audit-2026-10-25/pairs.json').read_text())['pairs']
    gold={x['pair_id']:x for x in json.loads((HERE.parent/'launchgate-reason-audit-2026-10-25/results.json').read_text())['pairs']}
    cases=[]; labels={}
    archive=HERE.parent/'launchgate-live-comparison-2026-10-25/run-02/outputs.tar.gz'
    assert digest(archive.read_bytes())=='fc471388468f06471c6a32d8e1bcc7fa54205431ba2a70b819bd411133cf5079'
    with tarfile.open(archive) as tar:
        rows=[json.loads(x) for x in tar.extractfile('out/main/runs.jsonl').read().splitlines()]
        for pair in pairs:
            row=next(x for x in rows if all(x[k]==v for k,v in pair['slot'].items()))
            assert row['continuation_calls']==1 and row['initial_answer']==pair['initial']['answer'] and digest(row['initial_answer'])==pair['initial']['answer_sha256']
            rid=row['request_ids']['initial']; assert re.fullmatch('[a-f0-9]{32}',rid)
            raw=tar.extractfile('out/relay/req/'+rid+'.json').read()
            assert digest(raw)==row['api_responses'][0]['metadata']['request_sha256']
            body=json.loads(raw); assert body['messages']==row['messages'] and len(body['messages'])==4
            fixture={**pair['fixture'],'records':row['tool_result']['hotels']}
            cases.append({'pair_id':pair['pair_id'],'slot':pair['slot'],'fixture':fixture,'tool_result':row['tool_result'],'base_body':body,
                          'initial_answer':row['initial_answer'],'initial_answer_sha256':row['initial_answer_sha256'],
                          'old_stop':row['hooks'][1]['output']})
            labels[pair['pair_id']]={'initial':gold[pair['pair_id']]['initial'],'old_disclosure_removed':gold[pair['pair_id']]['disclosure_removed']}
    assert len(cases)==12 and sum(x['initial']['grounding']=='contradicted' for x in labels.values())==4
    (HERE/'cases.json').write_text(json.dumps({'schema':'fresh-recheck-cases/1','source_archive_sha256':digest(archive.read_bytes()),'cases':cases},ensure_ascii=False,indent=2)+'\n')
    (HERE/'initial-labels.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n')
    print('Prepared 12 exact contexts and their captured historical Stop reasons.')

if __name__=='__main__':main()
