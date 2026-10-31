import importlib.util, pathlib,json,concurrent.futures
p=pathlib.Path(__file__).parent;sp=importlib.util.spec_from_file_location('capture',p/'fetch_public.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
tasks={
 'vulnetix5-comments':'https://api.github.com/repos/Vulnetix/advisory-database/issues/5/comments?per_page=100',
 'acs38-comments':'https://api.github.com/repos/GenAI-Security-Project/agent-control-standard/issues/38/comments?per_page=100',
 'hlido-scorecard':'https://raw.githubusercontent.com/ankitkapur1992-hlido/hlido-public/main/scorecards/alexar76-aimarket-plugins.json',
 'fplcat-histor-article':'https://fplcat.com/blog/ai-agents-playing-fantasy-premier-league',
 'sanka-histor':'https://sanka.com/research/apps/dataset/',
 'pypi-aimarket-histor':'https://pypi.org/pypi/aimarket-histor/json',
}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(m.fetch,tasks.items()))
(p/'http-final-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
