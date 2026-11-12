import json, sys
from collections import Counter, defaultdict

WALLETS = {  # the three textokit payers imokokok also names in alexar76/aimarket-hub#23
    "0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a",
    "0xa1d1c0cf717402ff3651aa4873ccf96410b01978",
    "0xc9c7b38c0942914fc8ea12063bc92dcd3b581670",
}
paid_by = defaultdict(set)
for log in json.load(open(sys.argv[1]))["logs"]:  # USDC Transfer logs, checked by verify_snapshot.py
    src, dst = ("0x" + t[-40:].lower() for t in log["topics"][1:3])
    if src in WALLETS and src != dst and int(log["data"], 16) > 0:
        paid_by[dst].add(src)
print("recipients:", len(paid_by))
for k, n in sorted(Counter(map(len, paid_by.values())).items()):
    print(f"paid by {k} of the 3:", n)
