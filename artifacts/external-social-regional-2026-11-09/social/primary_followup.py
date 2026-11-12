import urllib.request,urllib.error,pathlib,json,datetime,hashlib
root=pathlib.Path(__file__).parent;urls={'vibeleaderboard':'https://www.vibeleaderboard.ai/app/d8a7cafb-d59e-470a-9207-e89df4720091','witness-request-modern-tls':'https://lists.witness-network.org/mailman3/hyperkitty/list/participate%40lists.witness-network.org/thread/J5ZRRQ2EQRVIFF7LL23TWMTL4AVCLYNZ/'};out=[]
for k,u in urls.items():
 row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-social-audit/1.0'}),timeout=30)as x:b=x.read();row.update(status=x.status,final_url=x.url)
 except urllib.error.HTTPError as e:b=e.read();row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e);out.append(row);continue
 p=root/'raw'/(k+'.raw');p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());out.append(row)
(root/'primary-http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
