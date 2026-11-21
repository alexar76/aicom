# HISTOR subregistry article: data and checks (2026-11-21)

Article draft: PromoMaterials `devto/histor-subregistry-2026-11-21/`; blog post (draft) in
`modelmarket-blog/posts/a-copy-of-the-mcp-registry-that-remembers-what-each-servers-tools-list-returned/`.

| File | What |
|---|---|
| `walk.py`, `walk_segment.py`, `merge.py` | walk of `https://histor.modelmarket.dev/v0.1/servers?version=latest`: one walk from the start cut at `io.github.f/prompts.chat-mcp`, four segments from cursors `io.github.{f,k,p,u}/a:0` run in parallel (`segments.txt` names each segment's first entry), merged one line per name and version |
| `merged-2026-11-21.jsonl.gz` | the 69,634 latest entries as served, 17:02–17:11Z by the server's clock (`walk.log`; this Mac runs 57 min 58 s ahead) = `servers` of `/api/v1/subregistry` then |
| `count.py`, `counts-2026-11-21.json` | one category per server; `gunzip -c merged-2026-11-21.jsonl.gz > m.jsonl; python3 count.py m.jsonl walk.log` reproduces the JSON byte for byte |
| `make_figures.py` | `flow`, `coverage`, `cover` from the counts |
| `check_list.py`, `names.txt` | the article's reviewer script and its input (output in the article) |

The allow-listed copy in the article was run verbatim in an empty folder with Python 3.14 from the GitHub mirror at
`fb35e7a0681a3ec009d61ccf49ed1858ab6dbc63` (= main's `histor/` subregistry code, `subregistry.py` sha256 `ffb9a5a3…`):
sync `allow-list`, 3 pages, 3 stored, about 4 s; served on 127.0.0.1:9491 with the three entries and WARDEN's observation.
