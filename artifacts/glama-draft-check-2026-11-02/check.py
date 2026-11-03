"""Read-only verification of the November 2 snapshot. Never prints publisher identities."""
import collections
import gzip
import hashlib
import json
import re
from pathlib import Path

PREFIX = Path('/tmp/glama-2026-11-02-')
def path(name):
    return Path(str(PREFIX) + name)
def rows(name):
    with gzip.open(path(name + '.jsonl.gz'), 'rt') as f:
        for line in f:
            yield json.loads(line)
manifest = json.loads(path('manifest.json').read_text())
checksums = {}
for name in ['servers', 'changes', 'extras_changes']:
    filename = name + '.jsonl.gz'
    checksums[filename] = hashlib.sha256(path(filename).read_bytes()).hexdigest() == manifest['files'][filename]['sha256']
assert all(checksums.values()), checksums
servers = {s['id']: s for s in rows('servers')}
def host(s):
    return s['endpoint'].split('/')[2] if s['endpoint'].startswith('http') else None
hosts = collections.Counter(host(s) for s in servers.values() if host(s))
excluded = {h for h,n in hosts.items() if n in (1916,2365)}
assert len(excluded) == 2
changes = list(rows('changes'))
filtered = [c for c in changes if host(servers[c['serverId']]) not in excluded]
frequency = collections.Counter(c['serverId'] for c in filtered)
full = [c for c in filtered if json.loads(c['summaryJson']).get('detail') == 'full']
changed = {c['serverId'] for c in changes if json.loads(c['summaryJson']).get('detail') == 'full'}
cohort = [s for s in servers.values() if s['transport'] != 'stdio' and not s['delisted'] and s['toolSetDigest'] and s['firstPinned'] and s['firstPinned'] <= '2026-09-24T23:59:59Z']
description = missed = same_description_schema = only_description = cosmetic = directional = 0
word_bins = collections.Counter()
schema_entries = set()
directions = re.compile(r'\b(?:prefer|always|never|must|instead of|important|do not|don\x27t|only use|use this tool|before using|first call|recommended)\b', re.I)
for c in filtered:
    s = json.loads(c['summaryJson'])
    modified = s.get('modified', [])
    if any('description' in m.get('fields', {}) for m in modified): description += 1
    if s.get('detail') != 'full': continue
    if not s.get('added') and not s.get('removed') and not any('inputSchema' in m.get('fields', {}) for m in modified): missed += 1
    def structural_input_without_own_description(m):
        f = m.get('fields', {})
        if 'description' in f:
            return False
        for p in f.get('inputSchema', []):
            keys = re.findall(r'"([^"]+)"', p.get('path', ''))
            leaf = keys[-1] if keys else p.get('path', '')
            if leaf not in {'description','$schema','title','examples','$comment','$id'}:
                return True
        return False
    if any(structural_input_without_own_description(m) for m in modified):
        same_description_schema += 1
        schema_entries.add(c['serverId'])
    if not s.get('added') and not s.get('removed') and modified and all(set(m['fields']) == {'description'} for m in modified):
        only_description += 1
        before = ''.join(t for m in modified for op,t in m['fields']['description'] if op != '+')
        after = ''.join(t for m in modified for op,t in m['fields']['description'] if op != '-')
        edits = [t for m in modified for op,t in m['fields']['description'] if op in ('+', '-')]
        if all(re.fullmatch(r'[\s\d.,:\-/]*', t) for t in edits):
            cosmetic += 1
            continue
        words = sum(len(t.split()) for m in modified for op,t in m['fields']['description'] if op in ('+','-'))
        word_bins['1-2' if words <= 2 else '3-10' if words <= 10 else '11-50' if words <= 50 else '>50'] += 1
        if any(directions.search(t) for m in modified for op,t in m['fields']['description'] if op == '+'): directional += 1
versions = {}
for field in ['Server','Registry']:
    available = [c for c in filtered if servers[c['serverId']]['transport'] != 'stdio' and c.get('from'+field+'Version') is not None and c.get('to'+field+'Version') is not None]
    versions[field] = {'known': len(available), 'same':sum(c['from'+field+'Version'] == c['to'+field+'Version'] for c in available)}
def has_annotation_transition(c):
    for tool in json.loads(c['summaryJson']).get('tools', {}).values():
        annotations = tool.get('annotations', {})
        r, d = annotations.get('readOnlyHint'), annotations.get('destructiveHint')
        if (isinstance(r,list) and r[0] is True and r[1] is not True) or (isinstance(d,list) and d[0] is not True and d[1] is True):
            return True
    return False
escalations = [c for c in rows('extras_changes') if c['observedAt'] >= '2026-10-23' and has_annotation_transition(c)]
result = {
    'checksums': checksums,
    'total_changes':len(changes),
    'excluded_entries':sum(host(s) in excluded for s in servers.values()),
    'excluded_changes':len(changes)-len(filtered),
    'filtered_changes':len(filtered), 'filtered_changed_entries':len(frequency),
    'cohort':{'entries':len(cohort),'hosts':len({host(s) for s in cohort}), 'changed_hosts':len({host(s) for s in cohort if s['id'] in changed})},
    'changed_once':sum(n == 1 for n in frequency.values()),
    'seven_plus_entries':sum(n >= 7 for n in frequency.values()),
    'seven_plus_changes':sum(n for n in frequency.values() if n >= 7),
    'description_touched':description, 'full_comparisons':len(full), 'name_input_pin_misses':missed,
    'input_schema_without_own_description':same_description_schema,
    'input_schema_without_own_description_entries':len(schema_entries),
    'description_only':only_description, 'cosmetic':cosmetic,
    'word_bins':dict(word_bins),'directional':directional,
    'versions':versions,
    'annotation_escalation_changes':len(escalations),
    'annotation_escalation_entries':len({c['serverId'] for c in escalations}),
}
print(json.dumps(result,ensure_ascii=False,indent=2))
