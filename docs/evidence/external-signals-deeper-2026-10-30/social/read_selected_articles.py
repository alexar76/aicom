from fetch_public import get,ROOT
import json,re,time
ids=[4908243,4902690,4892562,4878922,4931640,4930765,4925388,4923609,4922244,4890721,4888293,4885921]
rows=[];matches=[]
for ident in ids:
 r=get(("dev-article-"+str(ident),"https://dev.to/api/articles/"+str(ident)));rows.append(r)
 if r.get("status")==429:break
 if r.get("status")==200:
  d=json.loads((ROOT/r["file"]).read_text());text=d.get("body_markdown","")
  contexts=[]
  for m in re.finditer(r"\bHISTOR\b|\bWARDEN\b|\bAIMarket\b|alexar76|modelmarket\.dev|attestedmemory",text,re.I):
   contexts.append(text[max(0,m.start()-180):m.end()+240])
  if contexts:matches.append({"id":ident,"url":d.get("url"),"title":d.get("title"),"published_at":d.get("published_at"),"edited_at":d.get("edited_at"),"contexts":contexts})
 time.sleep(1.5)
(ROOT/"article-http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
(ROOT/"article-keyword-matches.json").write_text(json.dumps(matches,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"reads":[{"key":r["key"],"status":r.get("status")} for r in rows],"matches":matches},ensure_ascii=False))

