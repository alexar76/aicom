"""Read new public candidates using the bounded local collector."""
from concurrent.futures import ThreadPoolExecutor
import json
from collect_sources import ROOT, fetch

TARGETS = {
    "ietf-linda-reply": "https://mailarchive.ietf.org/arch/msg/dawn/6m1_jcurI0F0_LadffO71f0d4m8/",
    "lupariel-hub": "https://lupariel.com/fichas/aimarket-hub/",
    "lupariel-hub-markdown": "https://lupariel.com/fichas/aimarket-hub.md",
    "one-gateway-market": "https://1gateway.dev/market/modelmarket.dev",
}
if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "followup-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
