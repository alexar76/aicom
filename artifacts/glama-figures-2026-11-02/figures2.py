import gzip, json, re, sys
from collections import Counter, defaultdict
from urllib.parse import urlparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'histor/scripts'))
import change_kinds as ck
d = sys.argv[1]
rows = lambda p: (json.loads(l) for l in gzip.open(f'{d}/{p}', 'rt'))
servers = {r['id']: r for r in rows('servers.jsonl.gz')}
host = lambda sid: (urlparse(servers[sid]['endpoint']).hostname if servers[sid]['endpoint'].startswith('http') else 'package')
BIG = {'gateway.pipeworx.io', 'agent-observatory-sensor.nolimit-observatory.workers.dev'}
ch = [c for c in rows('changes.jsonl.gz') if host(c['serverId']) not in BIG]
for c in ch: c['s'] = json.loads(c['summaryJson'])
pct = lambda a, b: round(100 * a / b, 1) if b else None
out = {}

def misses(s):
    if s.get('detail') != 'full' or s.get('added') or s.get('removed'): return False
    return not any('inputSchema' in (t.get('fields') or {}) for t in s.get('modified') or [])
per = defaultdict(list)
for c in ch:
    if c['s'].get('detail') == 'full': per[c['serverId']].append(misses(c['s']))
allmiss = sum(1 for v in per.values() if v and all(v)); anymiss = sum(1 for v in per.values() if any(v))
out['servers_schema_pin'] = {'changed_servers_full': len(per), 'every_change_missed': (allmiss, pct(allmiss, len(per))),
                             'at_least_one_missed': (anymiss, pct(anymiss, len(per)))}

# changes where a tool's input schema moved (beyond descriptions/cosmetics) while its description stayed
def param_only(s):
    if s.get('detail') != 'full': return False
    for t in s.get('modified') or []:
        f = t.get('fields') or {}
        if 'description' in f: continue
        if any(ck.leaf(e.get('path', '')) not in ({'description'} | ck.COSMETIC) for e in f.get('inputSchema') or []): return True
    return False
po = [c for c in ch if param_only(c['s'])]
out['param_moved_description_same'] = {'changes': len(po), 'servers': len({c['serverId'] for c in po})}

# description-only changes: how many words moved, and steering words added
STEER = re.compile(r'\b(prefer|always|never|must|instead of|important|do not|don\'t|only use|use this tool|before using|first call|recommended)\b', re.I)
buckets = Counter(); steer = 0; digits = 0
desc_only = [c for c in ch if ck.descriptions_only(c['s']) == 'tool']
for c in desc_only:
    words = 0; added = []
    for t in c['s']['modified']:
        for op in t['fields'].get('description') or []:
            if op[0] in '+-':
                words += len(op[1].split())
                if op[0] == '+': added.append(op[1])
    if all(ck.DIGITS.match(op[1]) for t in c['s']['modified'] for op in t['fields'].get('description') or [] if op[0] in '+-'):
        digits += 1; continue
    buckets['1-2' if words <= 2 else '3-10' if words <= 10 else '11-50' if words <= 50 else '51+'] += 1
    if any(STEER.search(a) for a in added): steer += 1
out['tool_description_only'] = {'changes': len(desc_only), 'digits_or_space_only': digits,
                                'words_moved': dict(buckets), 'adds_steering_word': (steer, pct(steer, len(desc_only) - digits))}

# annotation escalations (outside the digest)
ex = [e for e in rows('extras_changes.jsonl.gz')]
esc = [e for e in ex if json.loads(e['summaryJson']).get('escalations')]
out['escalations'] = {'all': len(esc), 'gateway': sum(host(e['serverId']) in BIG for e in esc),
                      'by_host_top': Counter(host(e['serverId']) for e in esc).most_common(5)}
smp = json.loads(esc[3]['summaryJson'])
out['escalation_example_keys'] = list(smp)
out['escalation_example'] = json.dumps(smp)[:900]
# how many escalations come with annotations removed entirely vs a hint flipped
flip = drop = destr = 0
for e in esc:
    s = json.loads(e['summaryJson'])
    for tool, moves in (s.get('tools') or {}).items():
        a = moves.get('annotations') if isinstance(moves, dict) else None
        txt = json.dumps(moves)
        if 'destructiveHint' in txt: destr += 1
        if 'readOnlyHint' in txt: flip += 1
out['escalation_mentions'] = {'readOnlyHint': flip, 'destructiveHint': destr}

cons = []
for e in ex:
    s_ = json.loads(e['summaryJson'])
    tools = []
    for tool in s_.get('escalations') or []:
        a = ((s_.get('tools') or {}).get(tool) or {}).get('annotations') or {}
        ro = a.get('readOnlyHint'); de = a.get('destructiveHint')
        if (isinstance(ro, list) and ro[0] is True and ro[1] is not True) or (isinstance(de, list) and de[1] is True and de[0] is not True):
            tools.append(tool)
    if tools: cons.append((e['serverId'], len(tools)))
out['escalations_checked'] = {'changes': len(cons), 'servers': len({s for s, _ in cons}), 'tools': sum(n for _, n in cons),
                              'servers_in_big_operators': len({s for s, _ in cons if host(s) in BIG}),
                              'package_changes': sum(1 for s, _ in cons if host(s) == 'package'),
                              'window': [min(e['observedAt'] for e in ex), max(e['observedAt'] for e in ex)]}
print(json.dumps(out, indent=1, default=str))
json.dump(out, open(sys.argv[2], 'w'), indent=1, default=str)
