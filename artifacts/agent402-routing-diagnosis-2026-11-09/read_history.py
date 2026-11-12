from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch
ROOT=Path(__file__).parent
OLD='48aff2412cd297da40eaadf3f61f25a5b1be2a68'
TASKS={
 'old-evidence-binding':'https://raw.githubusercontent.com/MikeyPetrillo/Agent402/'+OLD+'/src/evidence-binding.js',
 'old-seller-funding':'https://raw.githubusercontent.com/MikeyPetrillo/Agent402/'+OLD+'/src/seller-funding.js',
 'source-funding-latest':'https://api.github.com/repos/MikeyPetrillo/Agent402/commits?path=src/seller-funding.js&per_page=1',
 'source-evidence-history':'https://api.github.com/repos/MikeyPetrillo/Agent402/commits?path=src/evidence-binding.js&since=2026-10-29T00%3A00%3A00Z&per_page=100',
}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,TASKS.items()))
 (ROOT/'history-http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
