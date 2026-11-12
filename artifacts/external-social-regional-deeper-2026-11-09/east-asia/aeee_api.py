"""Read the public daily reports endpoint named by the site's own app.js."""
import datetime,hashlib,json,pathlib,urllib.request,urllib.error
R=pathlib.Path(__file__).parent;u='https://aeee.us/daily/api/reports';m={'name':'aeee-reports','url':u,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09'}),timeout=22)
except urllib.error.HTTPError as e:r=e
with r:
 b=r.read(8_000_000);(R/'raw'/'aeee-reports.raw').write_bytes(b);m.update(status=r.code,headers=dict(r.headers),final_url=r.url,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
(R/'aeee-index.json').write_text(json.dumps([m],indent=2));print(json.dumps(m,indent=2))
