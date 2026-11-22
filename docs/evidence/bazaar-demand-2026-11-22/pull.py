import json,urllib.request,time,sys
out=[];off=0;total=None
while total is None or off<total:
    for attempt in range(4):
        try:
            r=urllib.request.urlopen(urllib.request.Request(f"https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000&offset={off}",headers={"User-Agent":"x402-survey/1.0"}),timeout=90)
            d=json.load(r); break
        except Exception as e:
            time.sleep(3*(attempt+1)); d=None
    if d is None: print("fail at",off); break
    total=d["pagination"]["total"]; out+=d["items"]; off+=1000
    time.sleep(0.4)
slim=[{"resource":i.get("resource"),"description":(i.get("description") or "")[:300],"quality":i.get("quality") or {},"accepts":[{k:a.get(k) for k in ("amount","asset","network","payTo","scheme")} for a in (i.get("accepts") or [])],"lastUpdated":i.get("lastUpdated")} for i in out]
json.dump({"fetched_total":len(slim),"reported_total":total,"items":slim},open("bazaar-slim.json","w"))
print(len(slim),total)
