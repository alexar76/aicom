"""Tokens (o200k) a client sends per tool list: name, description, input schema per tool (as histor/scripts/tool_list_tokens.py)."""
import gzip, json, sys
from concurrent.futures import ThreadPoolExecutor
import tiktoken
enc = tiktoken.get_encoding('o200k_base')
d, out = sys.argv[1], sys.argv[2]
def sent(tools):
    return [{'name': t.get('name'), 'description': t.get('description') or '', 'input_schema': t.get('inputSchema') or {'type': 'object'}} for t in tools]
def count(line):
    r = json.loads(line)
    tools = json.loads(r['toolsJson'])
    if isinstance(tools, dict): tools = tools.get('tools') or []
    s = sent(tools)
    total = len(enc.encode(json.dumps(s, ensure_ascii=False, separators=(',', ':')), disallowed_special=()))
    return r['digest'], total, len(tools)
res = {}
with gzip.open(f'{d}/toolsets.jsonl.gz', 'rt') as fh, ThreadPoolExecutor(8) as pool:
    batch = []
    for line in fh:
        batch.append(line)
        if len(batch) >= 2000:
            for dg, n, k in pool.map(count, batch): res[dg] = (n, k)
            batch = []
            print(len(res), file=sys.stderr, flush=True)
    for dg, n, k in pool.map(count, batch): res[dg] = (n, k)
json.dump(res, open(out, 'w'))
print('toolsets', len(res))
