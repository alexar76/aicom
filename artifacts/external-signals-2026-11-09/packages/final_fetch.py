"""Public GET-only namespace and external observer-method verification."""
import concurrent.futures,json,pathlib,urllib.parse
import fetch
R=pathlib.Path(__file__).parent
tasks={
 'pypi-aimarket-bridges':'https://pypi.org/pypi/aimarket-bridges/json',
 'deps-pypi-awr':'https://deps.dev/_/s/pypi/p/awr/v/2.0.1/dependents',
 'overall-awr':'https://pypistats.org/api/packages/awr/overall?mirrors=false',
 'shortformkit-build-current':'https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/scripts/make_directory.py',
 'shortformkit-probe-current':'https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/scripts/probe.py',
}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: rows=list(pool.map(fetch.fetch,tasks.items()))
(R/'final-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps([{k:r[k] for k in ('name','status','error') if k in r} for r in rows],indent=2))
