"""Two public GETs requested for research distribution indicators."""
import concurrent.futures,json,pathlib
import fetch
R=pathlib.Path(__file__).parent
tasks={
 'hf-histor':'https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions',
 'openalex-histor':'https://api.openalex.org/works/W7223029314',
}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(fetch.fetch,tasks.items()))
(R/'research-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps([{k:r[k] for k in ('name','status','error') if k in r} for r in rows],indent=2))
