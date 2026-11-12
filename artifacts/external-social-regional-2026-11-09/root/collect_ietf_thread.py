"""Read observed follow-up links from the archived DAWN thread."""
import concurrent.futures
import json
from collect_sources import ROOT, fetch

TARGETS = {
    "ietf-own-followup": "https://mailarchive.ietf.org/arch/msg/dawn/vGzlv459xuo1ICC5gcJIW-K4NTU/",
    "ietf-du-reply": "https://mailarchive.ietf.org/arch/msg/dawn/GbumKwLL1oy3I7h7GFmgAkNJAkQ/",
    "ietf-riccardo": "https://mailarchive.ietf.org/arch/msg/dawn/4tX94aUiEaWi1W23dHA1jIw_6jo/",
}

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "ietf-http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
