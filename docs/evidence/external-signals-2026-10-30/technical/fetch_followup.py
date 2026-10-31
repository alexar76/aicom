import importlib.util, pathlib,json,concurrent.futures,urllib.parse
p=pathlib.Path(__file__).parent
sp=importlib.util.spec_from_file_location('capture',p/'fetch_public.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
tasks={
 'genai105-comments':'https://api.github.com/repos/GenAI-Security-Project/GenAI-Red-Team-Lab/issues/105/comments?per_page=100',
 'mcpcost7-comments':'https://api.github.com/repos/ondraulehla/mcpcost/issues/7/comments?per_page=100',
 'next-store28-comments':'https://api.github.com/repos/myoshi2891/Next-Store/issues/28/comments?per_page=100',
 'next-store28-reviews':'https://api.github.com/repos/myoshi2891/Next-Store/pulls/28/comments?per_page=100',
 'agentdojo235-comments':'https://api.github.com/repos/ethz-spylab/agentdojo/issues/235/comments?per_page=100',
 'github-participated-recent':'https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':'commenter:alexar76 -user:alexar76 updated:>=2026-10-28','sort':'updated','order':'desc','per_page':100}),
 'deps-warden-082':'https://api.deps.dev/v3alpha/systems/npm/packages/%40aimarket%2Fwarden/versions/0.8.2:dependents',
 'deps-warden-current':'https://api.deps.dev/v3alpha/systems/npm/packages/%40aimarket%2Fwarden/versions/0.22.2:dependents',
 'deps-histor-current':'https://api.deps.dev/v3alpha/systems/pypi/packages/histor/versions/0.5.0:dependents',
 'deps-aimarket-agent':'https://api.deps.dev/v3alpha/systems/pypi/packages/aimarket-agent/versions/2.6.0:dependents',
 'glama-warden':'https://glama.ai/mcp/servers/alexar76/warden',
 'smithery-warden':'https://smithery.ai/server/@alexar76/warden',
 'pulsemcp-warden':'https://www.pulsemcp.com/servers/alexar76-warden',
 'protocolprobe-memory':'https://protocolprobe.com/mcp/servers/io.github.alexar76/attested-memory',
 'hlido-repo':'https://api.github.com/repos/ankitkapur1992-hlido/hlido-public/git/trees/main?recursive=1',
}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(m.fetch,tasks.items()))
(p/'http-followup-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
