from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch
ROOT=Path(__file__).parent
TASKS={
    'crawlcheck-continuity':'https://raw.githubusercontent.com/emmanuelorta/crawlcheck-core/main/sdk/src/continuity.js',
    'crawlcheck-py-lock':'https://raw.githubusercontent.com/emmanuelorta/crawlcheck-core/main/sdk-python/crawlcheck/lock.py',
    'crawlcheck-vectors':'https://raw.githubusercontent.com/emmanuelorta/crawlcheck-core/main/sdk/test/fixtures/continuity.json',
    'crawlcheck-commits':'https://api.github.com/repos/emmanuelorta/crawlcheck-core/commits?since=2026-11-07T00%3A00%3A00Z&per_page=100',
    'histor-crawlcheck-record':'https://histor.modelmarket.dev/api/v1/servers?q=io.github.emmanuelorta/crawlcheck',
}
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,TASKS.items()))
    (ROOT/'crawlcheck-reads-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
