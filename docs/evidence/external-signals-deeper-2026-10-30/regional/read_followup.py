from read_native import get,ROOT
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import json
tasks=[
("hatena-dev-runtime","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh"})),
("hatena-dev-cost","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://dev.to/alexar76/what-an-mcp-servers-tool-list-costs-we-counted-the-tokens-of-34374-of-them-3011"})),
("hatena-dev-dataset","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://dev.to/alexar76/45-of-remote-mcp-servers-changed-their-tool-definitions-in-four-weeks-the-log-is-now-a-dataset-2mhe"})),
("zenn-histor-api","https://zenn.dev/api/search?"+urlencode({"q":"HISTOR","source":"articles","order":"latest"})),
("zenn-alexar-api","https://zenn.dev/api/search?"+urlencode({"q":"alexar76","source":"articles","order":"latest"})),
("zenn-aimarket-scraps","https://zenn.dev/api/search?"+urlencode({"q":"aimarket","source":"scraps","order":"latest"})),
("habr-v2-modelmarket","https://habr.com/kek/v2/articles/?"+urlencode({"query":'"modelmarket.dev"',"fl":"ru","hl":"ru"})),
]
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
(ROOT/"native-followup-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(rows,ensure_ascii=False))

