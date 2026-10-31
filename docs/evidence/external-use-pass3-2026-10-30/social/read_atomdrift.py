"""New public Atomdrift publication surfaces, GET only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import hashlib,json,re,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
TASKS=[("atomdrift-feed","https://atomdrift.org/feed.xml"),("atomdrift-home","https://atomdrift.org/")]
def get(task):
 name,url=task;row={"name":name,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public read-only research)"}),timeout=25) as r:
   raw=r.read(3000001);row.update(status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),truncated=len(raw)>3000000)
  file=name+(".xml" if name.endswith("feed") else ".html")
  (ROOT/file).write_bytes(raw);row["file"]=file
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=="__main__":
 if "--offline" in sys.argv:
  rows=json.loads((ROOT/"http-index.json").read_text())
 else:
  with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(get,TASKS))
  (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 facts={"reads":rows}
 f=ROOT/"atomdrift-feed.xml"
 if f.exists():
  try:
   xml=ET.fromstring(f.read_bytes());ns={"a":"http://www.w3.org/2005/Atom"};items=xml.findall("a:entry",ns);facts["feed_items"]=len(items)
   facts["feed_updated"]=xml.findtext("a:updated",namespaces=ns)
   facts["matching_items"]=[{"title":i.findtext("a:title",namespaces=ns),"url":i.find("a:link",ns).get("href"),"date":i.findtext("a:updated",namespaces=ns)} for i in items if re.search(r"\bwarden\b|\baimarket\b|alexar76|modelmarket\.dev|attestedmemory",ET.tostring(i,encoding="unicode"),re.I)]
  except Exception as e:facts["parse_error"]=str(e)
 f=ROOT/"atomdrift-home.html"
 if f.exists():
  text=f.read_text()
  facts["social_links"]=sorted(set(re.findall(r'https?://(?:www\.)?(?:x\.com|twitter\.com|bsky\.app|mastodon\.social|linkedin\.com)/[^" <>\s]+',text)))
 (ROOT/"atomdrift-facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(facts,ensure_ascii=False,indent=2))

