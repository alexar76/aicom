#!/usr/bin/env python3
"""Read only public frozen HISTOR snapshot metadata on admin-vps; never run packages."""
import json
from pathlib import Path
import subprocess

REMOTE = r'''
import gzip,hashlib,json,re
from pathlib import Path
p=Path('/var/lib/histor-datasets/2026-10-20')
assert hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest() == 'a7bfc9e09ab9782157ad6c7a4bb136477609746a7e7e6f9c6695ea2012e926fc'
def rows(name):
    with gzip.open(p/name, 'rt') as f:
        for line in f: yield json.loads(line)
servers={x['id']:x for x in rows('servers.jsonl.gz')}
patterns=[r'without asking',r'never ask the user',r'already approved',r'skip confirmation',r'prefer this over',r'use this tool instead',r'web search',r'before calling any other',r'approval',r'confirmation',r'ignore previous',r'do not ask',r'auto.?approve']
rx=re.compile('|'.join(patterns),re.I)
out=[]
for c in rows('changes.jsonl.gz'):
    server=servers[c['serverId']]
    # Snapshot rows distinguish package-backed transports from HTTP endpoints;
    # only npm-backed rows are candidates, not native KyttoMCP app versions.
    npm=server.get('registry') == 'npm' or 'npm' in str(server.get('endpoint','')) or str(server.get('name','')).startswith('npm:')
    if not npm: continue
    summary=json.loads(c['summaryJson'])
    matches=[]
    for tool in summary.get('modified',[]):
        ops=(tool.get('fields') or {}).get('description',[])
        additions=''.join(str(v) for op,v in ops if op=='+')
        full=''.join(str(v) for op,v in ops if op in ('+','='))
        for pattern in patterns:
            m=re.search(pattern,additions,re.I)
            if m:
                matches.append({'tool':tool.get('name',tool.get('tool')), 'modifiedRecordKeys':list(tool), 'descriptionOps':ops,'pattern':pattern,'addedExcerpt':additions[max(0,m.start()-180):m.end()+220],'newDescriptionFromSummary':full[:3000]})
                break
    if matches:
        out.append({'change':{k:c.get(k) for k in ('id','serverId','observedAt','fromToolSetDigest','toToolSetDigest','fromSubjectDigest','toSubjectDigest')},'server':server,'summaryDetail':summary.get('detail'),'matches':matches,'added':summary.get('added'),'removed':summary.get('removed')})
print(json.dumps({'snapshot':'2026-10-20','manifestSHA256':hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest(),'candidateCount':len(out),'candidates':out},ensure_ascii=False))
'''

if __name__ == '__main__':
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                             'admin-vps', 'python3 -'], input=REMOTE, text=True,
                            capture_output=True, check=True)
    data = json.loads(result.stdout)
    # Manual shortlist favours compact packages and interpretable approval flows.
    # Matching words are a search aid, not evidence of an attack.
    pool_path = Path(__file__).with_name('candidate-pool.json')
    pool_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    selected = [17172, 20433, 23671, 21268, 17171, 19685, 19868, 17800,
                18145, 20934, 20942, 21028, 21163, 21528, 23756, 21351,
                20473, 22275, 22241, 17293]
    by_id = {row['change']['id']: row for row in data['candidates']}
    data['poolCount'] = data['candidateCount']
    data['candidates'] = [by_id[event_id] for event_id in selected]
    data['candidateCount'] = len(data['candidates'])
    data['selection'] = 'Manual shortlist; top 3 fetched as full raw toolsets. Keyword matches alone do not identify attacks.'
    destination = Path(__file__).with_name('candidates.json')
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'candidateCount': data['candidateCount'], 'output': str(destination)}))
