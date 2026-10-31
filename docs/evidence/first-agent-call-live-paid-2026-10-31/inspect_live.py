from pathlib import Path
import datetime,json,httpx
from aimarket_agent import A2AClient
R=Path(__file__).resolve().parent
secret=json.loads(Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json').read_text())
with httpx.Client(timeout=35) as c:
 r=c.get('https://modelmarket.dev/ai-market/v2/account',headers={'X-API-Key':secret['api_key']});r.raise_for_status();a=r.json();(R/'account-after-example.json').write_text(json.dumps(a,indent=2)+'\n');print('account:',json.dumps(a))
client=A2AClient('https://modelmarket.dev')
try:
 for name,kw in [('local',{'hub':'local'}),('all',{})]:
  d=client.search('gaia weather open-meteo',budget=0.01,limit=50,**kw)
  (R/f'weather-search-{name}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
  print(name, json.dumps([{k:m.get(k) for k in ('product_id','capability_id','source_hub','price_per_call_usd','credits_eligible')} for m in d['matches']]))
finally: client.close()
