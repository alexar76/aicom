"""Figures for the Glama fact sheet from a HISTOR snapshot (servers, changes, extras_changes). Standard library."""
import gzip, json, sys
from collections import Counter, defaultdict
from urllib.parse import urlparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'histor/scripts'))
import change_kinds as ck

d = sys.argv[1]
rows = lambda p: (json.loads(l) for l in gzip.open(f'{d}/{p}', 'rt'))
servers = {r['id']: r for r in rows('servers.jsonl.gz')}
ch = list(rows('changes.jsonl.gz'))
for c in ch:
    c['s'] = json.loads(c['summaryJson'])
    c['k'] = ck.kind(c['s'])
def host(sid):
    e = servers[sid]['endpoint']
    return urlparse(e).hostname if e.startswith('http') else 'package'
out = {}
pct = lambda a, b: round(100 * a / b, 1) if b else None

# operators: hosts with many registry entries
eps = Counter(host(s['id']) for s in servers.values() if s['endpoint'].startswith('http') and not s['delisted'])
chh = Counter(host(c['serverId']) for c in ch)
big = [(h, eps[h], chh[h], pct(chh[h], len(ch))) for h, _ in chh.most_common(6)]
out['top_hosts_by_changes'] = big
BIG = {'gateway.pipeworx.io', 'agent-observatory-sensor.nolimit-observatory.workers.dev'}

def schema_pin_misses(s):
    """A pin over tool names + inputSchema fires on add/remove or any inputSchema path; else it misses."""
    if s.get('detail') != 'full':
        return None
    if s.get('added') or s.get('removed'):
        return False
    for t in s.get('modified') or []:
        if 'inputSchema' in (t.get('fields') or {}):
            return False
    return True

def tool_desc_touched(s):
    return s.get('detail') == 'full' and any('description' in (t.get('fields') or {}) for t in s.get('modified') or [])

def param_desc_touched(s):
    if s.get('detail') != 'full': return False
    for t in s.get('modified') or []:
        for e in (t.get('fields') or {}).get('inputSchema') or []:
            if ck.leaf(e.get('path', '')) == 'description': return True
    return False

def param_only_edits(s):
    """Tool edits whose description stayed and whose input schema moved beyond descriptions/cosmetics."""
    n = 0
    if s.get('detail') != 'full': return 0
    for t in s.get('modified') or []:
        f = t.get('fields') or {}
        if 'description' in f: continue
        if any(ck.leaf(e.get('path', '')) not in ({'description'} | ck.COSMETIC) for e in f.get('inputSchema') or []):
            n += 1
    return n

def block(cs, label):
    full = [c for c in cs if c['s'].get('detail') == 'full']
    r = {'changes': len(cs), 'servers': len({c['serverId'] for c in cs}), 'full': len(full)}
    r['kinds'] = {k: (n, pct(n, len(cs))) for k, n in Counter(c['k'] for c in cs).most_common()}
    only = Counter(ck.descriptions_only(c['s']) for c in cs)
    r['descriptions_only_tool'] = (only['tool'], pct(only['tool'], len(cs)))
    r['descriptions_only_tool_or_param'] = (only['tool'] + only['param'], pct(only['tool'] + only['param'], len(cs)))
    td = sum(tool_desc_touched(c['s']) for c in cs)
    tpd = sum(tool_desc_touched(c['s']) or param_desc_touched(c['s']) for c in cs)
    r['tool_description_touched'] = (td, pct(td, len(cs)))
    r['tool_or_param_description_touched'] = (tpd, pct(tpd, len(cs)))
    miss = [c for c in full if schema_pin_misses(c['s'])]
    r['schema_pin_misses'] = (len(miss), pct(len(miss), len(full)), 'of full-detail changes')
    nm = sum(1 for c in full if not (c['s'].get('added') or c['s'].get('removed')))
    r['name_pin_misses'] = (nm, pct(nm, len(full)))
    po = [(c['serverId'], param_only_edits(c['s'])) for c in cs]
    r['param_only_tool_edits'] = (sum(n for _, n in po), len({s for s, n in po if n}), 'tool edits, servers')
    # versions
    for kind in ('remote', 'package'):
        sub = [c for c in cs if (host(c['serverId']) == 'package') == (kind == 'package')]
        both = [c for c in sub if c.get('fromServerVersion') and c.get('toServerVersion')]
        same = sum(c['fromServerVersion'] == c['toServerVersion'] for c in both)
        rb = [c for c in sub if c.get('fromRegistryVersion') and c.get('toRegistryVersion')]
        rsame = sum(c['fromRegistryVersion'] == c['toRegistryVersion'] for c in rb)
        r[f'version_{kind}'] = {'changes': len(sub), 'serverInfo_both': len(both), 'serverInfo_same': (same, pct(same, len(both))),
                                'registry_both': len(rb), 'registry_same': (rsame, pct(rsame, len(rb)))}
    per = Counter(c['serverId'] for c in cs)
    r['servers_changed_once'] = (sum(1 for n in per.values() if n == 1), len(per))
    r['servers_7plus'] = (sum(1 for n in per.values() if n >= 7), sum(n for n in per.values() if n >= 7))
    out[label] = r

block(ch, 'all')
block([c for c in ch if host(c['serverId']) not in BIG], 'without_two_operators')

# remote servers pinned on the first day, as change_kinds does; changed = any non-names change
first_day = min(c['observedAt'] for c in ch)[:10] + 'T23:59:59Z'
per_kinds = defaultdict(Counter)
for c in ch:
    per_kinds[c['serverId']][c['k']] += 1
def cohort(pred, label):
    g = [r for r in servers.values() if pred(r) and not r['delisted'] and r['toolSetDigest'] and r['firstPinned'] and r['firstPinned'] <= first_day]
    changed = [r for r in g if any(n for k, n in per_kinds[r['id']].items() if k != 'names')]
    subst = [r for r in g if any(n for k, n in per_kinds[r['id']].items() if k not in ('names', 'noise'))]
    out[label] = {'pinned_first_day': len(g), 'changed': (len(changed), pct(len(changed), len(g))),
                  'changed_beyond_noise': (len(subst), pct(len(subst), len(g))),
                  'added_or_removed_tool': sum(1 for r in g if per_kinds[r['id']]['addrm'])}
cohort(lambda r: r['transport'] != 'stdio', 'remote_cohort')
cohort(lambda r: r['transport'] != 'stdio' and host(r['id']) not in BIG, 'remote_cohort_without_two_operators')
out['first_day'] = first_day
out['big_operator_endpoints'] = {h: eps[h] for h in BIG}

# annotations (not in the digest): escalations
import os
ex = list(rows('extras_changes.jsonl.gz')) if os.path.exists(f'{d}/extras_changes.jsonl.gz') else []
esc = [e for e in ex if (json.loads(e['summaryJson']).get('escalations'))]
if not ex: ex = [{'serverId': '', 'observedAt': ''}]
out['extras_changes'] = {'changes': len(ex), 'servers': len({e['serverId'] for e in ex}),
                         'from': min(e['observedAt'] for e in ex), 'until': max(e['observedAt'] for e in ex),
                         'escalations': len(esc), 'escalation_servers': len({e['serverId'] for e in esc}),
                         'escalation_sample': json.loads(esc[0]['summaryJson']).get('escalations') if esc else None}
json.dump(out, open(sys.argv[2], 'w'), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
