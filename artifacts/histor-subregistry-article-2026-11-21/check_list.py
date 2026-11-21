"""For each server name in a file, print what HISTOR recorded about its latest registry version.

    python3 check_list.py names.txt
Python 3.9+, standard library only. Reads https://histor.modelmarket.dev/v0.1/servers/{name}/versions/latest.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://histor.modelmarket.dev/v0.1/servers/"
KEY = "dev.modelmarket.histor/observed"

for line in open(sys.argv[1]):
    name = line.split("#", 1)[0].strip()
    if not name:
        continue
    url = BASE + urllib.parse.quote(name, safe="") + "/versions/latest"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            entry = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"{name}: {e.code} (not in the registry copy)")
        continue
    print(f"{name} {entry['server']['version']}")
    observed = entry["_meta"].get(KEY)
    if not observed:
        print("  no observation yet")
        continue
    for t in observed["targets"]:
        if t["toolCount"] is not None:
            print(f"  {t['endpoint']}: {t['toolCount']} tools, changed {t['changes']}x, "
                  f"unchanged since {t['unchangedSince']}, read {t['lastObserved']}")
        else:
            print(f"  {t['endpoint']}: not read ({t['notAttempted'] or t['lastStatus']})")
