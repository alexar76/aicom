"""Read only advertised public discovery/manifest metadata at our known domains."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent
HOSTS={'modelmarket.dev','hub.modelmarket.dev','hunt.modelmarket.dev'}

def get(url):
    out={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 public metadata research'}),timeout=25) as response:
            raw=response.read();out.update(status=response.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),final_url=response.url)
        data=json.loads(raw)
        return out,data
    except urllib.error.HTTPError as error:out.update(status=error.code,error=str(error))
    except Exception as error:out.update(status=None,error=str(error))
    return out,None

def relevant(value):
    text=json.dumps(value,ensure_ascii=False).lower()
    return any(word in text for word in ['industrial-platform','industrial_platform','industrial-sentinel','industrial platform sentinel','1f21.up.railway.app'])

if __name__=='__main__':
    discoveries=['https://'+host+'/.well-known/ai-market.json' for host in sorted(HOSTS)]
    records=[];manifest_urls=set()
    with ThreadPoolExecutor(max_workers=3) as pool:
        reads=list(pool.map(get,discoveries))
    for (record,data),url in zip(reads,discoveries):
        if isinstance(data,dict):
            record['selected']={key:data.get(key) for key in ['name','protocol_versions','manifest_url','capabilities_count','federated_capabilities_count','ecosystem']}
            record['peer_matches']=[peer for peer in (data.get('peers') or []) if relevant(peer)]
            record['observed_hub_matches']=[hub for hub in (data.get('observed_hubs') or []) if relevant(hub)]
            link=urllib.parse.urljoin(url,data.get('manifest_url') or '')
            if data.get('manifest_url') and urllib.parse.urlsplit(link).hostname in HOSTS:manifest_urls.add(link)
        records.append(record)
    with ThreadPoolExecutor(max_workers=3) as pool:
        reads=list(pool.map(get,sorted(manifest_urls)))
    for record,data in reads:
        if isinstance(data,dict):
            record['selected']={key:data.get(key) for key in ['protocol_version','generated_at','capabilities_count','local_capabilities','federated_capabilities','hubs_indexed','base_url']}
            tools=data.get('tools') or [];by_hub=data.get('by_hub') or {}
            record['tools_returned']=len(tools)
            record['tool_matches']=[tool for tool in tools if relevant(tool)]
            record['hub_matches']={key:value for key,value in by_hub.items() if relevant([key,value])} if isinstance(by_hub,dict) else [hub for hub in by_hub if relevant(hub)]
        records.append(record)
    (ROOT/'hub-discovery-scope.json').write_text(json.dumps({'scope':'Only advertised public discovery and same-ecosystem advertised manifest URLs. Absence from these snapshots does not establish absence from private/runtime peer databases.','records':records},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(records,ensure_ascii=False)[:16000])
