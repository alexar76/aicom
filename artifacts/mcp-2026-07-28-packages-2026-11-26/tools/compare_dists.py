"""compare_dists.py OURS_DIR THEIRS_DIR — same-named wheels and sdists, file by file (names and sha256).

Run with `python3 -I`: the second directory holds files downloaded from an index.
"""
import hashlib, sys, tarfile, zipfile
from pathlib import Path


def wheel(path):
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith("/")}


def sdist(path):
    out = {}
    with tarfile.open(path) as t:
        for m in t:
            if m.isfile():
                out[m.name] = hashlib.sha256(t.extractfile(m).read()).hexdigest()
    return out


ours, theirs = Path(sys.argv[1]), Path(sys.argv[2])
bad = 0
for name in sorted(p.name for p in ours.iterdir() if p.suffix in (".whl", ".gz")):
    if not (theirs / name).exists():
        print(f"{name}: missing on the other side"); bad += 1
        continue
    read = wheel if name.endswith(".whl") else sdist
    a, b = read(ours / name), read(theirs / name)
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    differ = sorted(n for n in set(a) & set(b) if a[n] != b[n])
    bad += len(only_a) + len(only_b) + len(differ)
    print(f"{name}: ours {len(a)} files, theirs {len(b)}; only ours {len(only_a)}, only theirs {len(only_b)}, differing {len(differ)}")
    for label, names in (("only ours", only_a), ("only theirs", only_b), ("differ", differ)):
        for n in names[:25]:
            print(f"   {label}: {n}")
sys.exit(1 if bad else 0)
