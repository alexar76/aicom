import urllib.request,urllib.error,urllib.parse,json,pathlib,datetime,hashlib
root=pathlib.Path(__file__).parent;token='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';addresses={'payout':'0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a','agent402':'0x77065d81e18ad403BCD6e9A0616b288e16744121'};out=[]
for k,a in addresses.items():
 u='https://base.blockscout.com/api/v2/addresses/'+a+'/token-transfers?type=ERC-20&token='+token;row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-chain-audit/1.0'}),timeout=35)as res:b=res.read();row['status']=res.status
  p=root/'raw'/(k+'-page1.json');p.write_bytes(b);row.update(file=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
 except urllib.error.HTTPError as e:row.update(status=e.code,error=str(e));(root/'raw'/(k+'-error.raw')).write_bytes(e.read())
 except Exception as e:row['error']=str(e)
 out.append(row)
(root/'http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
