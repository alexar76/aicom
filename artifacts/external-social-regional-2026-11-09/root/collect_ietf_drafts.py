"""Save the published versions linked by the IETF Datatracker."""
import concurrent.futures
import json
from collect_sources import ROOT, fetch

TARGETS = {
    "ietf-mdi-01": "https://www.ietf.org/archive/id/draft-cui-dawn-mdi-model-01.txt",
    "ietf-mdi-02": "https://www.ietf.org/archive/id/draft-cui-dawn-mdi-model-02.txt",
    "ietf-datatracker": "https://datatracker.ietf.org/doc/draft-cui-dawn-mdi-model/",
}

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "ietf-draft-http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
