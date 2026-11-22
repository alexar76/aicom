import json,collections
from urllib.parse import urlsplit
d=json.load(open("bazaar-slim.json"))["items"]
USDC={"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}
def price(i):
    for a in i["accepts"]:
        if (a.get("asset") or "").lower() in USDC and a.get("amount"):
            try: return int(a["amount"])/1e6
            except: pass
    return None
rows=[]
for i in d:
    q=i["quality"]; rows.append((q.get("l30DaysTotalCalls") or 0,q.get("l30DaysUniquePayers") or 0,urlsplit(i["resource"] or "").hostname or "?",i["resource"],i["description"],price(i)))
N=len(rows); calls=sum(r[0] for r in rows)
print("listings",N,"30d calls",calls)
buckets=collections.Counter()
for r in rows:
    p=r[1]; buckets["0" if p==0 else "1" if p==1 else "2-9" if p<10 else "10-99" if p<100 else "100+"]+=1
print("unique payers per listing:",dict(buckets))
hosts=collections.defaultdict(lambda:[0,0,0,0.0])
for c,p,h,res,desc,pr in rows:
    hosts[h][0]+=c; hosts[h][1]=max(hosts[h][1],p); hosts[h][2]+=1; hosts[h][3]+=c*(pr or 0)
top=sorted(hosts.items(),key=lambda kv:-kv[1][0])
print("hosts",len(hosts),"top10 share of calls",round(sum(v[0] for _,v in top[:10])/calls,3))
print("\nTOP 30 HOSTS by 30d calls: host | calls | max unique payers on one listing | listings | est. USD (calls×listed price)")
for h,v in top[:30]: print(f"{h} | {v[0]} | {v[1]} | {v[2]} | {v[3]:.0f}")
print("\nTOP 40 LISTINGS by unique payers:")
for c,p,h,res,desc,pr in sorted(rows,key=lambda r:-r[1])[:40]: print(f"{p} payers | {c} calls | ${pr} | {res[:70]} | {desc[:80]}")
json.dump(sorted(rows,key=lambda r:-r[1])[:400],open("top400.json","w"))
