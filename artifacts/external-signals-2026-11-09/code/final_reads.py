from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import fetch
ROOT=Path(__file__).parent
TASKS={
    'crawlcheck-spec':'https://crawlcheck.io/spec/mcp-lockfile',
    'crawlcheck-tree':'https://api.github.com/repos/emmanuelorta/crawlcheck-core/git/trees/main?recursive=1',
    'registry82-comments':'https://api.github.com/repos/modelcontextprotocol/registry/issues/82/comments?per_page=100',
    'agentavow240':'https://api.github.com/repos/AgentAvow/AgentAvow/issues/240',
    'agentavow240-comments':'https://api.github.com/repos/AgentAvow/AgentAvow/issues/240/comments?per_page=100',
    'ragmap-servers':'https://raw.githubusercontent.com/khalidsaidi/ragmap/main/data/servers.json',
}
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,TASKS.items()))
    (ROOT/'final-reads-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
