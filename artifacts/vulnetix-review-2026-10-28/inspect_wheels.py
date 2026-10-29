import concurrent.futures, hashlib, io, json, urllib.request, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
SOURCES = {
 'aimarket-mcp': {'aimarket_mcp/server.py':'aimarket-mcp/aimarket_mcp/server.py','aimarket_mcp/security.py':'aimarket-mcp/aimarket_mcp/security.py'},
 'skopos-fleet': {'skopos/remediation/git_push.py':'skopos/skopos/remediation/git_push.py','skopos/auth_store.py':'skopos/skopos/auth_store.py'},
 'aimarket-platon': {'platon/main.py':'platon/backend/platon/main.py'},
 'aimarket-oracle-core': {'oracle_core/app.py':'oracles/core/oracle_core/app.py'},
 'aimarket-logos': {'logos/app.py':'logos/logos/app.py','logos/main.py':'logos/logos/main.py'},
 'aimarket-metis': {'metis/api/auth.py':'metis/metis/api/auth.py'},
 'aimarket-treasury': {'treasury/service.py':'treasury/treasury/service.py'},
 'aimarket-atlas': {'atlas/delivery.py':'atlas/atlas/delivery.py'},
 'aimarket-hestia': {'hestia/domains.py':'hestia/hestia/domains.py'},
}
summary = json.loads((ROOT/'registry-summary.json').read_text())
def inspect(item):
 name = item['package']; wheel = item['wheels'][0]
 with urllib.request.urlopen(wheel['url'],timeout=45) as r: raw=r.read()
 digest=hashlib.sha256(raw).hexdigest()
 assert digest==wheel['digests']['sha256'], name+' wheel hash mismatch'
 out={'package':name,'version':item['version'],'sha256_verified':True,'members':[]}
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  for member,local in SOURCES[name].items():
   if member not in z.namelist():
    out['members'].append({'member':member,'missing':True,'candidates':[n for n in z.namelist() if n.endswith('/'+member.split('/')[-1])]});continue
   content=z.read(member); source=(WORKSPACE/local).read_bytes()
   evidence=ROOT/'wheel-source'/name/member
   evidence.parent.mkdir(parents=True,exist_ok=True);evidence.write_bytes(content)
   text=content.decode()
   out['members'].append({'member':member,'local_path':local,'identical_to_workspace':content==source,'wheel_sha256':hashlib.sha256(content).hexdigest(),'workspace_sha256':hashlib.sha256(source).hexdigest(),'has_local_unverified_setting':'LOCAL_UNVERIFIED' in text,'has_local_relay_setting':'LOCAL_RELAY' in text,'has_explicit_trusted_proxies':'TRUSTED_PROXIES' in text,'has_loopback_host_setting':'LOGOS_HOST' in text,'has_explicit_loopback_hostkey_skip':'SKOPOS_GIT_SKIP_HOST_KEY_LOOPBACK' in text})
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: out=list(pool.map(inspect,summary['packages']))
(ROOT/'wheel-verification.json').write_text(json.dumps(out,indent=2)+'\n')
for row in out:print(row['package'],row['version'],'sha256 OK',[(v['member'],v.get('identical_to_workspace'),v.get('missing',False)) for v in row['members']])
