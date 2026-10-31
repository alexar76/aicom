from fetch_public import get,ROOT
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
import json
feed=json.loads((ROOT/"raw/bsky-authorfeed.json").read_text())["feed"]
tasks=[]
for r in feed:
 p=r["post"];uri=p["uri"];key=uri.rsplit("/",1)[-1]
 if p.get("replyCount",0):tasks.append(("bsky-thread-"+key,"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?"+urlencode({"uri":uri,"depth":10,"parentHeight":10})))
 if p.get("repostCount",0):tasks.append(("bsky-reposted-"+key,"https://public.api.bsky.app/xrpc/app.bsky.feed.getRepostedBy?"+urlencode({"uri":uri,"limit":100})))
with ThreadPoolExecutor(max_workers=2) as p:rows=list(p.map(get,tasks))
(ROOT/"thread-http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
own="did:plc:u63726gke7rdfrsrtuz3hqzd"
external=[];counts={"threads_requested":0,"own_posts_in_threads":0,"external_posts_in_threads":0,"reposts_requested":0}
def walk(t):
 if not isinstance(t,dict):return
 p=t.get("post")
 if p:
  if p.get("author",{}).get("did")!=own:
   counts["external_posts_in_threads"]+=1;external.append({"uri":p.get("uri"),"author":p.get("author",{}).get("handle"),"createdAt":p.get("record",{}).get("createdAt"),"text":p.get("record",{}).get("text")})
  else:counts["own_posts_in_threads"]+=1
 for r in t.get("replies",[]):walk(r)
for r in rows:
 if r.get("status")!=200:continue
 d=json.loads((ROOT/r["file"]).read_text())
 if "thread" in d:
  counts["threads_requested"]+=1;walk(d["thread"])
 elif "repostedBy" in d:
  counts["reposts_requested"]+=1
  print("REPOSTED",r["key"],[(p.get("did"),p.get("handle")) for p in d["repostedBy"]])
out={"counts":counts,"external_posts":external}
(ROOT/"bsky-thread-summary.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(out,ensure_ascii=False))

