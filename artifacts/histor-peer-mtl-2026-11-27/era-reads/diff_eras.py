"""diff_eras.py DIR NAME MODE_A MODE_B — where two saved tools/list reads of one server differ (contract fields)."""
import json, sys
from pathlib import Path

d, name, a, b = Path(sys.argv[1]), sys.argv[2].replace("/", "__"), sys.argv[3], sys.argv[4]
A = {t["name"]: t for t in json.loads((d / f"{name}.{a}.tools.json").read_text())}
B = {t["name"]: t for t in json.loads((d / f"{name}.{b}.tools.json").read_text())}
print(f"{sys.argv[2]}: {a} has {len(A)} tools, {b} has {len(B)}; only in {a}: {sorted(set(A)-set(B))}; only in {b}: {sorted(set(B)-set(A))}")


def walk(x, y, path, out):
    if type(x) is not type(y):
        out.append((path, x, y)); return
    if isinstance(x, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x: out.append((f"{path}.{k}", "<absent>", y[k]))
            elif k not in y: out.append((f"{path}.{k}", x[k], "<absent>"))
            else: walk(x[k], y[k], f"{path}.{k}", out)
    elif isinstance(x, list):
        if len(x) != len(y): out.append((path, x, y)); return
        for i, (p, q) in enumerate(zip(x, y)): walk(p, q, f"{path}[{i}]", out)
    elif x != y:
        out.append((path, x, y))


for n in sorted(set(A) & set(B)):
    out = []
    walk(A[n], B[n], n, out)
    for path, x, y in out[:6]:
        print(f"  {path}\n      {a}: {json.dumps(x, ensure_ascii=False)[:260]}\n      {b}: {json.dumps(y, ensure_ascii=False)[:260]}")
    if len(out) > 6: print(f"  … {len(out)-6} more differences in {n}")
