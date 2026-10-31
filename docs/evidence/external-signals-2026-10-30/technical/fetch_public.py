"""Read-only public URL capture for external-signal audit; only urllib GET."""
import concurrent.futures,datetime,hashlib,json,pathlib,re,urllib.request,urllib.error,urllib.parse
ROOT=pathlib.Path(__file__).parent
TASKS={
 'github-issues-alexar76':'https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':'"alexar76" -user:alexar76 -author:alexar76','sort':'updated','order':'desc','per_page':100}),
 'github-issues-modelmarket':'https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':'"modelmarket.dev" -user:alexar76 -author:alexar76','sort':'updated','order':'desc','per_page':100}),
 'github-issues-warden':'https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':'"@aimarket/warden" -user:alexar76 -author:alexar76','sort':'updated','order':'desc','per_page':100}),
 'github-issues-histor':'https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':'"histor.modelmarket.dev" -user:alexar76 -author:alexar76','sort':'updated','order':'desc','per_page':100}),
 'github-readmes':'https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':'alexar76 in:readme -user:alexar76','sort':'updated','order':'desc','per_page':100}),
 'github-mcp3431':'https://api.github.com/repos/modelcontextprotocol/modelcontextprotocol/issues/3431/comments?per_page=100',
 'github-agentmesh561':'https://api.github.com/repos/google/agentmesh/issues/561/comments?per_page=100',
 'github-histor-pr14':'https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14',
 'github-mcpmoat-competitors':'https://raw.githubusercontent.com/Ducarv/mcpmoat/dev/docs/competitors.md',
 'github-rugsnare-readme':'https://raw.githubusercontent.com/Paraphern/rugsnare/main/README.md',
 'github-rugsnare-shopify':'https://raw.githubusercontent.com/Paraphern/rugsnare/main/docs/servers/shopify.md',
 'industrial-requirements':'https://raw.githubusercontent.com/industrial-platform-ai/industrial-platform-agent-tools/main/aimarket-sentinel/requirements.txt',
 'industrial-discovery':'https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json',
 'industrial-manifest':'https://x402-gateway-production-1f21.up.railway.app/ai-market/v2/manifest',
 'pypi-histor':'https://pypi.org/pypi/histor/json',
 'pypi-aimarket-hub':'https://pypi.org/pypi/aimarket-hub/json',
 'pypi-aimarket-agent':'https://pypi.org/pypi/aimarket-agent/json',
 'npm-warden':'https://registry.npmjs.org/@aimarket%2fwarden/latest',
 'npm-warden-downloads':'https://api.npmjs.org/downloads/point/last-week/@aimarket%2fwarden',
 'hf-histor':'https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions',
 'openalex-histor':'https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760',
 'protocolprobe':'https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security',
 'canopii':'https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins/2.1.2',
 'odel':'https://odel.app/modules/alexar76',
 'smallprint-warden':'https://smallprint.dev/a/npm/%40aimarket/warden',
}
def fetch(t):
 name,url=t; meta={'name':name,'url':url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'alexar76-external-readonly-audit/2026-10-30','Accept':'application/json,text/html,text/plain;q=0.9,*/*;q=0.8'}),timeout=30) as r:
   data=r.read(8_000_000); meta.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()); (ROOT/(name+'.raw')).write_bytes(data)
 except urllib.error.HTTPError as e: meta.update(status=e.code,error=str(e))
 except Exception as e: meta['error']=repr(e)
 return meta
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: result=list(pool.map(fetch,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False,indent=2))
