from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch
ROOT=Path(__file__).parent
d=json.loads((ROOT/'source-commit.raw').read_text());sha=d['sha']
FILES=['src/dispatch-eligibility.js','src/settlement-proof.js','src/seller-funding.js','src/base-unproven.js','src/leaderboard.js','src/evidence-binding.js','src/x402-index.js','src/tools/route-execute.js','src/index.js','scripts/test-dispatch-eligibility.js','scripts/test-unproven-lane-labels.js','scripts/test-seller-funding.js']
if __name__=='__main__':
 tasks={x.replace('/','--'):'https://raw.githubusercontent.com/MikeyPetrillo/Agent402/'+sha+'/'+x for x in FILES}
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,tasks.items()))
 (ROOT/'source-http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'source-pin.json').write_text(json.dumps({'sha':sha,'date':d['commit']['committer']['date'],'url':d['html_url']},indent=2)+'\n')
 print(json.dumps(rows,ensure_ascii=False,indent=2))
