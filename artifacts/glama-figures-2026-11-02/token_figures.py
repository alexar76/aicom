"""Token figures from tokens.py's output: current tool lists, and how changes moved the cost. Standard library.

    python3 token_figures.py SNAPSHOT_DIR tokens-1102.json token-figures-1102.json
"""
import gzip, json, statistics, sys
from collections import defaultdict
from urllib.parse import urlparse

d, tok_path, out_path = sys.argv[1:4]
tok = json.load(open(tok_path))
rows = lambda p: (json.loads(l) for l in gzip.open(f'{d}/{p}', 'rt'))
servers = {r['id']: r for r in rows('servers.jsonl.gz')}
BIG = {'gateway.pipeworx.io', 'agent-observatory-sensor.nolimit-observatory.workers.dev'}
def host(r):
    return urlparse(r['endpoint']).hostname if r['endpoint'].startswith('http') else 'package'
def pctl(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p / 100 * len(xs)))] if xs else None
out = {}
for kind in ('remote', 'package'):
    xs = [tok[r['toolSetDigest']][0] for r in servers.values()
          if not r['delisted'] and r['toolSetDigest'] in tok and host(r) not in BIG
          and (host(r) == 'package') == (kind == 'package') and tok[r['toolSetDigest']][1] > 0]
    out[f'current_{kind}'] = {'servers': len(xs), 'p50': pctl(xs, 50), 'p75': pctl(xs, 75), 'p90': pctl(xs, 90),
                              'p99': pctl(xs, 99), 'max': max(xs), 'over_10k': sum(x > 10_000 for x in xs),
                              'over_25k': sum(x > 25_000 for x in xs), 'over_50k': sum(x > 50_000 for x in xs)}
deltas = []; per_server = defaultdict(list)
for c in rows('changes.jsonl.gz'):
    r = servers[c['serverId']]
    if host(r) in BIG or c['fromToolSetDigest'] not in tok or c['toToolSetDigest'] not in tok:
        continue
    if json.loads(c['summaryJson']).get('detail') != 'full':
        continue
    a, b = tok[c['fromToolSetDigest']][0], tok[c['toToolSetDigest']][0]
    deltas.append(b - a); per_server[c['serverId']].append((c['observedAt'], a, b))
grow = [x for x in deltas if x > 0]; shrink = [x for x in deltas if x < 0]
out['changes'] = {'counted': len(deltas), 'grew': len(grow), 'shrank': len(shrink), 'same': deltas.count(0),
                  'growth_p50': pctl(grow, 50), 'growth_p90': pctl(grow, 90), 'growth_p99': pctl(grow, 99),
                  'moved_over_1000': sum(abs(x) > 1000 for x in deltas), 'grew_over_1000': sum(x > 1000 for x in grow),
                  'net_sum': sum(deltas)}
net = []
for sid, seq in per_server.items():
    seq.sort(); net.append(seq[-1][2] - seq[0][1])
out['servers_net'] = {'servers': len(net), 'grew': sum(x > 0 for x in net), 'shrank': sum(x < 0 for x in net),
                      'grew_p50': pctl([x for x in net if x > 0], 50), 'grew_over_1000': sum(x > 1000 for x in net),
                      'doubled': sum(1 for seq in per_server.values() if seq[0][1] and seq[-1][2] >= 2 * seq[0][1])}
json.dump(out, open(out_path, 'w'), indent=1)
print(json.dumps(out, indent=1))
