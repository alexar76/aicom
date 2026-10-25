# HISTOR 0.3.0 — what a tool list costs, part by part

A client resends every connected server's tool list with each model request. HISTOR counted those lists in
October (median about 1,300 tokens, [docs/tool-list-cost.md](https://github.com/alexar76/histor/blob/main/docs/tool-list-cost.md));
this release says where the tokens are and what each release did to them.

## The split

Every count is split into the tool names, the descriptions, the input schemas, and the keys and punctuation
around them; the four add up to the total. Output schemas and the list as listed are reported beside it.
Each top-level property of an input schema is counted as well, so a diff names the field that grew.
`@playwright/mcp`, as HISTOR last observed it: 3,762 tokens, 3,123 of them input schemas. In one night's crawl
(22 to 23 October) 95 of 109 changes made a list heavier; one package added a `raw` flag to all 15 of its
tools, 708 tokens per request.

## Per change, for every server in the log

| Path | What |
| --- | --- |
| `/api/v1/changes/<id>/cost` | every total before and after, tools added and removed, each tool whose count moved |
| `/api/v1/servers/<id>/cost` | the current list per tool, and the totals of its last changes |
| `/api/v1/cost/toolsets/<digest>` | the cost of one stored tool set |

## In your own CI

```bash
pip install "aimarket-histor[cost]"
histor tool-cost snapshot --stdio "node dist/index.js" -o tool-cost.json      # commit it
histor tool-cost check --baseline tool-cost.json --stdio "node dist/index.js" --max-increase 10%
```

`check` writes a Markdown table to the job summary and exits 1 when the total, the descriptions or the input
schemas grow past the limit, each checked on its own. `--budget N` caps the whole list; `--update` accepts a
growth; `diff A B` compares two snapshots or saved lists. The tools come from a stdio command, a streamable
HTTP endpoint or a saved tools/list.

## A restart no longer costs the crawl

A redeploy or a crash continues the interrupted crawl where it stopped: what was read is not dialled again,
however long the cycle has been running; the packages keep the cycle's plan and budget (no hour of version
lookups after each restart); and the run's numbers survive, so `/api/v1/stats` reports the whole cycle.
Migration 012 adds `crawl_plans`.

Count one list without installing anything: [modelmarket.dev/tools/tool-list-cost](https://modelmarket.dev/tools/tool-list-cost?utm_source=github&utm_medium=release&utm_campaign=histor-0.3.0)
