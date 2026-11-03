# robots.txt on MCP hosts: the old Python reader against RFC 9309 (2026-11-01)

The ScraperWatch cross-check found one MCP server that a crawler skipped although its robots.txt allows it
(www.apier.no, `Allow: /api/mcp$`). The crawler used Python's `urllib.robotparser`. This folder asks how often the old
and the RFC 9309 reading disagree on MCP endpoints.

Published at https://histor.modelmarket.dev/datasets/robots-mcp-hosts-2026-11-01/. License: CC BY 4.0. The panel is
ScraperWatch's.

## What changed in Python

`urllib.robotparser` follows RFC 9309 since gh-138907 (Serhiy Storchaka, merged to main 2026-05-04): the longest
matching rule wins, Allow wins a tie, `*` matches any run of characters and a trailing `$` anchors the end. Before,
the first matching rule in file order won and `*` and `$` were ordinary characters. Checked in the tagged sources:

| Release | Reader |
|---|---|
| 3.15.0 (2026-10-09) | RFC 9309 |
| 3.14.5 (2026-05-10) and later | RFC 9309 |
| 3.14.0 – 3.14.4 | old |
| 3.13.14 (2026-06-10) and later | RFC 9309 |
| 3.13.0 – 3.13.13 | old |
| 3.12.13 and every older line | old |

## Inputs

- `panel.txt`: ScraperWatch's fixed panel, 2,995 MCP endpoints drawn at random from the official registry
  (https://scraperwatch.com/mcp-changes/panel.txt, sha256 936b0ae3…), 2,347 distinct hosts.
- `fetch.sh`: one GET of `https://<host>/robots.txt` per host on 2026-11-01 between 19:06 and 19:10Z, redirects
  followed, 10 s limit, first 512 KiB, user agent `HISTOR-robots-survey/2026-11-01`. The responses are packed in
  `raw.tar.gz` (sha256 5e3a6f04…e485, 2,347 `<host>.meta` files (status, final URL, type) and 2,245 `<host>.txt` bodies);
  `tar xzf raw.tar.gz` restores `raw/`, which `analyze.py` reads.

## Method

`analyze.py decide` asks `urllib.robotparser` of the interpreter that runs it whether a crawler with no group of
its own (`ExampleBot`, so the `*` group applies) may fetch each endpoint URL:
- `old.json`: Python 3.12.13 (old reader);
- `new.json`: Python 3.14.8 (RFC 9309 reader).

`analyze.py compare` counts the differences, adds HISTOR's own reader (`histor.peer_xcheck.robots_allows`) as a third
opinion and writes `results.json` and `disagreements.csv`. A body that is an HTML page or has no `User-agent` line
counts as no rules.

```bash
tar xzf raw.tar.gz
python3.12 -I analyze.py decide old.json
python3.14 -I analyze.py decide new.json
python3 -I analyze.py compare old.json new.json ../../histor
```

## Results

| | |
|---|---:|
| hosts | 2,347 |
| robots.txt answered 200/206 | 1,576 |
| …of those, real robots.txt with groups | 1,315 |
| …an HTML page or no groups | 261 |
| 404 | 514 |
| no answer, 4xx other than 404, 5xx | 257 |
| endpoints on hosts with a robots.txt | 1,764 |
| disallowed for `ExampleBot` by RFC 9309 (Python 3.14.8) | 421 |
| disallowed by the old reader (Python 3.12.13) | 173 |
| **endpoints where the two readers disagree** | **252** (14.3%) |
| …old reader allows, RFC 9309 disallows | 250 |
| …old reader disallows, RFC 9309 allows | 2 |
| hosts with at least one disagreement | 237 of 1,315 (18.0%) |
| HISTOR's reader against Python 3.14.8 | 0 disagreements |

Why they disagree:
- 218 of 252: rule order. Typically `Allow: /` comes first, then `Disallow: /api/`, and the endpoint is `/api/mcp`.
  The first rule matches, so the old reader allows; the longer rule wins under RFC 9309. 619 of the 1,315 files
  put `Allow: /` before at least one Disallow in the group that applies.
- The rule RFC 9309 applies on the 250 endpoints the old reader wrongly allows (`deciding_disallow` in
  `results.json`): a `/api` prefix on 159; a rule that names the MCP path itself (`/mcp`, `/mcp/`, `/mcp$`,
  `/api/v1/mcp` and the like) on 85; `/v1/`, `/gw/` or `/sse` on 6.
- 34 of 252: a `*` or `$` in a rule that matches. The two that the old reader disallows are both written for
  agents: www.apier.no (`Allow: /api/mcp$` before `Disallow: /api/`) and api.adplug.app (`Allow: /mcp/linkedin-ads$`
  before `Disallow: /mcp`). The old reader takes `$` literally, so the Allow never matches.

142 of the 1,315 files use `*` or `$` in the group that applies.

## What this does not say

- A `Disallow` in these files was mostly written for search engines (`/api/`, `/dashboard`, `/admin`). Whether an
  MCP client or a monitor should honour it for an endpoint the publisher listed in the MCP registry is a separate
  question; the numbers only say what each reader decides. (HISTOR itself honours robots.txt since 2 November 2026,
  05:40Z: the `histor` group, else `*`, read by RFC 9309.)
- One read per host from one network, on one day. A few hosts answer differently by user agent or region.
- Only the `*` group was asked. A crawler with a named group in a file can get a different answer.

## Cite

Artamokhov, A. (2026). robots.txt on MCP hosts: the old Python reader against RFC 9309, 1 Nov 2026. HISTOR.
https://histor.modelmarket.dev/datasets/robots-mcp-hosts-2026-11-01/
