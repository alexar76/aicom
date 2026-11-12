"""Read catalogue detail links observed in the saved index pages."""
from concurrent.futures import ThreadPoolExecutor
import json
from collect_sources import ROOT, fetch
TARGETS = {
    "agents-shipped-aicom": "https://agentsshipped.com/l/alexar76-aicom",
    "anclum-aimarket-plugins": "https://anclum.com/zh/s/alexar76-aimarket-plugins/",
}
if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "detail-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(rows,ensure_ascii=False,indent=2))
