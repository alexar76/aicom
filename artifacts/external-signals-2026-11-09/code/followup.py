from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch

ROOT=Path(__file__).parent
TASKS={
    'forge-histor-api':'https://theagentforge.io/api/v1/check?id=github.com%2Falexar76%2Fhistor',
    'forge-histor-page':'https://theagentforge.io/t/github.com%2Falexar76%2Fhistor',
    'ragmap-readme':'https://raw.githubusercontent.com/khalidsaidi/ragmap/main/README.md',
    'ragmap-tree':'https://api.github.com/repos/khalidsaidi/ragmap/git/trees/main?recursive=1',
    'industrial-health':'https://x402-gateway-production-1f21.up.railway.app/health',
    'industrial-wellknown':'https://x402-gateway-production-1f21.up.railway.app/.well-known/x402',
}
for key, repo, number in [
    ('acs38','GenAI-Security-Project/agent-control-standard',38),
    ('owasp33','OWASP/secure-agent-playbook',33),
    ('agentmesh561','google/agentmesh',561),
    ('mcp3431','modelcontextprotocol/modelcontextprotocol',3431),
    ('swarm467','datafund/swarm_connect',467),
]:
    base='https://api.github.com/repos/'+repo+'/issues/'+str(number)
    TASKS[key]=base
    TASKS[key+'-comments']=base+'/comments?per_page=100'

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,TASKS.items()))
    (ROOT/'followup-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
