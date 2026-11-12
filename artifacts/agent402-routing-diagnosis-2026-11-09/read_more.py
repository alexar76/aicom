from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch
ROOT=Path(__file__).parent
sha=json.loads((ROOT/'source-pin.json').read_text())['sha']
TASKS={
 'src--server.js':'https://raw.githubusercontent.com/MikeyPetrillo/Agent402/'+sha+'/src/server.js',
 'route-warden-q':'https://agent402.tools/api/route?q=WARDEN&include=external',
 'leaderboard-all':'https://agent402.tools/api/leaderboard?include=all&top=10000&sort=calls&window=7d',
 'source-dispatch-history':'https://api.github.com/repos/MikeyPetrillo/Agent402/commits?path=src/dispatch-eligibility.js&since=2026-10-29T00%3A00%3A00Z&per_page=100',
 'source-funding-history':'https://api.github.com/repos/MikeyPetrillo/Agent402/commits?path=src/seller-funding.js&since=2026-10-29T00%3A00%3A00Z&per_page=100',
}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,TASKS.items()))
 (ROOT/'more-http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
