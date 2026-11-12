"""Follow source links already observed on the candidate pages; public GET only."""
from concurrent.futures import ThreadPoolExecutor
import json
from collect_candidates import ROOT, fetch

TARGETS = {
    'agentrank-attested': 'https://agentrank-ai.com/tool/alexar76--attested-memory/',
    'agentrank-metis': 'https://agentrank-ai.com/tool/alexar76--metis/',
    'agentrank-hub': 'https://agentrank-ai.com/tool/alexar76--aimarket-hub/',
    'agentrank-agent': 'https://agentrank-ai.com/tool/alexar76--aimarket-agent/',
}
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(fetch,TARGETS.items()))
    (ROOT/'followup-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
