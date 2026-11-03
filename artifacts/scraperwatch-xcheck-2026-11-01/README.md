# ScraperWatch MCP tool-change log vs HISTOR, same endpoints, 31 Oct and 1 Nov 2026

ScraperWatch (scraperwatch.com/mcp-changes/, started 2026-10-30) reads a fixed panel of 3,000 remote endpoints from
the registry snapshot of 2026-10-30. The run is once a day at about 02:50Z: `initialize`, `notifications/initialized`
and `tools/list` with pagination. It publishes daily diffs: tools added and removed, and per changed tool the field
diffs as JSON paths with old and new values. HISTOR reads the same endpoints about every 30 minutes (some every 6 h)
and stores every definition it was served.

## Inputs

| File | What | sha256 |
|---|---|---|
| `changes.json` | ScraperWatch log, fetched 2026-11-01 ~10:04Z (local clock; the file says last update 2026-11-01) | `41190f42…85585` |
| `changes.csv` | same, one row per tool change | `802bb33b…36a6` |
| `histor-export.jsonl.gz` | HISTOR prod (admin-vps Postgres), read-only: the 110 endpoints, observations/changes/extras changes since 2026-10-29, and the blobs they reference (`export.sql`) | `07ae4118…34d3` |

Rerun with `python3 -I xcheck.py changes.json histor-export.jsonl.gz > results.json`.

## Method

For every ScraperWatch tool change on day D, the window runs from D−1 02:50Z to D 02:50Z, with 7 h of slack on each
side. The check is item by item: every tool added or removed, and every field path. The item counts as seen when
HISTOR has a read with the old value followed by a read with the new one inside the window.

Three rules make HISTOR's copy comparable with ScraperWatch's paths:
- **Absent vs null.** A member that is absent equals ScraperWatch's `null`.
- **Schemas.** They are indexed after resolving local `$ref` and sorting lists at any depth. This is how ScraperWatch
  numbers them: `anyOf[3]` is the fourth branch after sorting, and enums come alphabetical.
- **Title and annotations.** These come from HISTOR's extras digest, merged into the tool.

## Results (`results.json`)

All 110 endpoints in the ScraperWatch log are HISTOR targets.

| ScraperWatch tool-change records | 98 |
|---|---|
| Same change in HISTOR, path by path | **64** (738 items, 56 endpoints) |
| Server `instructions` only (HISTOR does not record them) | 5 |
| Not seen as a change in HISTOR | 4 |
| HISTOR has no definitions in the window | 25 |

**The 4 not seen.** None of them contradicts ScraperWatch:
- **emberverse, switchapp, wudao-mcp.** HISTOR held no digest for these until MTL/1.1 went live on 2026-10-31 at
  16:42Z (fractional numbers). Its first stored copy is already ScraperWatch's new side.
- **www.ghlagencymcp.com.** It answered HISTOR with 308 redirects, which HISTOR does not follow, and HISTOR did not
  read it again until 10-31 13:26Z. HISTOR's reads before (10-29) and after (10-31 13:26Z) both match ScraperWatch's
  new side. ScraperWatch's old side matches what the sister entry ghlagencymcp.com serves.

**The 25 without definitions.**
- **7 records:** the same pre-MTL/1.1 gap (10-31, fractions).
- **18 records on 15 endpoints:** HISTOR failed where ScraperWatch read the tools.
  - `http-401`: 9 records on 6 endpoints.
  - `protocol`: 8 records on 8 endpoints:
    - "HTTP error did not match our request id; no downgrade" ×4;
    - "modern discovery did not advertise the requested version" ×2;
    - "no mutually supported modern protocol version; no downgrade" ×1;
    - "malformed JSON-RPC error response; no downgrade" ×1.
  - `http-400`: 1.

**Timing.** For the 64 matches, HISTOR first had the new side a median 7.2 h before ScraperWatch's read (max 23.5 h).
In 5 matches HISTOR's first new read came after 02:50Z, because ScraperWatch's run is not exactly at 02:50.

**The other direction.** This is only possible on the 110 endpoints known to be in the panel, because the panel
list is not published. HISTOR recorded 5 changes on them that the daily diffs do not list:
- **openbait and senado.** The changes fell minutes around 02:50Z, so they land on different days.
- **kaleto and radix.** The changes came on 10-30 at 08:11Z and 07:33Z, probably before ScraperWatch's first
  baseline read; its time is not published.
- **theagentsbay.** HISTOR lacks a definition at one of the two read times.

None of the five is a miss on ScraperWatch's side.

## Finding: HISTOR's modern-first handshake drops servers it used to read (since 2026-10-29)

Prod `histor/mcpclient.py::_discover` opens with the 2026-07-28 `server/discover`. It falls back to `initialize`
only on an "identifiable legacy rejection": HTTP 400, 404 or 405 with a JSON-RPC error −32600, −32601 or −32602
whose id matches ours. Two manual checks on 2026-11-01:

- **mcp.kaiku.tech/mcp.** `server/discover` gets 401: «A Bearer token is required for anything but the
  introduction (initialize, tools/list)». `initialize` 2025-06-18 gets a result. HISTOR stops at the 401.
- **mcp.quotewise.io.** `server/discover` gets 400 with
  `{"id":"server-error","error":{"code":-32600,"message":"Bad Request: Unsupported protocol version: 2026-07-28. Supported versions: 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25"}}`.
  This is a textbook legacy rejection. HISTOR refuses to downgrade only because the id is `"server-error"`.
  `initialize` gets a result.

**Prod scale** (`gap.sql`, `gap3.sql`, read-only, 2026-11-01). Remote targets (not stdio) that read OK on 2026-10-28
and had no OK read since 2026-10-30, by current status:

| Status | Detail | Targets |
|---|---|---:|
| protocol | HTTP error did not match our request id; no downgrade | 789 |
| http-401 | (probably mostly discover-only auth, like kaiku) | 719 |
| protocol | modern discovery did not advertise the requested version | 304 |
| protocol | malformed JSON-RPC error response; no downgrade | 120 |
| protocol | no mutually supported modern protocol version; no downgrade | 37 |
| protocol | modern server/discover returned MCP error −32020; no downgrade | 14 |

Per day, remote targets with a `protocol` status went from 105 on 10-28 to 914 on 10-29 and 1,585 on 10-30. Targets
with any `ok` read, stdio included, fell from about 28,200 on 10-29 to about 23,000 on 10-31.

**Fix (2026-11-01, local, not deployed).** `histor/mcpclient.py` follows the specification's HTTP rule:
a first modern request refused with a 4xx that carries no recognized modern error means a legacy server, and the
reader falls back to `initialize` once. The cases:
- **Statuses.** 400/404/405, and 401/403.
- **Error bodies.** A legacy code under a foreign id, or a body that is not JSON-RPC.
- **Version lists.** An unsupported-version error or discovery result listing only pre-2026-07-28 versions.
- **Not a discovery result.** A `server/discover` reply that is no DiscoverResult.
- **The first `tools/list`.** A refusal of that page before anything is read; marx.finance advertises 2026-07-28,
  then refuses it.

These still stop: rate limits, timeouts, 5xx, redirects, recognized modern errors and ambiguous bodies.
`docs/mcp-compatibility.md` describes the rule.

Checks:
- **Tests.** The HISTOR suite passes: 1,050 passed, 244 skipped. The rewritten and added cases reproduce kaiku,
  quotewise, civai, trendsapi, xdata and marx.
- **Live, from the Mac, with the patched reader.** All 15 endpoints that prod HISTOR failed on in this comparison
  now read `ok`, with 6 to 392 tools: kaiku, quotewise, civai, trendsapi, trendsmcp, xdata, marx, viridis
  ghg-ledger, hail, spawnpop, duvo, btcdecoded, fundinglandscape, retrodiffusion, plus arcadeindex as a control.
  HISTOR is a passive reader that sends no credentials, so falling back costs one extra request and nothing else.

**Separately.** HISTOR does not record the server's `instructions` from `initialize`. ScraperWatch tracks them: 30 of
its 98 records change them, on 27 endpoints in two days.

## Both directions, rerun 2026-11-01 with ScraperWatch's panel list

ScraperWatch replied on 2026-11-01 at 10:35, from Wren, the AI that operates it. It confirmed our counts (110
endpoints, 98 tool-change records, 36 status transitions) and published the panel:
https://scraperwatch.com/mcp-changes/panel.txt. The file has 2,995 of the 3,000 endpoints (sha256 936b0ae3…) and is
copied in `reverse/`. Their baseline run was 2026-10-30 10:49:43–10:59:39Z; later runs start at 02:50Z and use
protocol 2025-06-18, initialize and tools/list. They skip endpoints that robots.txt disallows.

**Their log against HISTOR**, rerun with the real baseline (`PREV_READ` in `xcheck.py`): unchanged. 64 of 98 match
path by path (738 items); `results.json` is regenerated.

**HISTOR against their panel** (`reverse/xcheck_reverse.py`, inputs and `reverse.json` in `reverse/`). HISTOR recorded
a change on 292 endpoint-days of the panel; 67 of them are in their log. For each of the other 225, HISTOR's
definitions were compared at the times of their two reads:

| Endpoint-days | Why the daily diff does not show it |
|---:|---|
| 202 | only members they do not hash changed: 199 on gateway.pipeworx.io, whose tools carry their own `version` member moving about every 6 h; 3 `_meta` |
| 12 | robots.txt disallows the endpoint (RFC 9309: longest match, Allow on a tie) |
| 6 | changed and came back between their two reads |
| 1 | only numbers in a schema changed (they leave counters out) |
| 2 | may predate their baseline: mcp.stackenhance.com and theagentsbay.com changed on 30 Oct between HISTOR reads at 06:57/06:12Z and 12:59/12:13Z |
| 1 | HISTOR had no read before their earlier read (mcp.bitview.space) |
| 1 | **looks like a miss** |

The miss is https://www.apier.no/api/mcp (no.apier/mcp). HISTOR saw two changes:
- `get_company_verification` (`mode` description) changed on 31 Oct between HISTOR reads at 01:19 and 07:19Z;
- `get_company_authority` (description) changed between 31 Oct 19:23Z and 1 Nov 01:23Z.

Either way, at least one of their two daily diffs should list it, and neither does. Its robots.txt disallows `/api/`
but allows `/api/mcp$`. A parser without the `$` end anchor would skip it.

Also worth a look: theagentsbay.com is in their log on 1 Nov as `ok -> robots_disallowed`. Its robots.txt as read on
1 Nov ~10:30Z allows `/mcp/public/` for every agent.

**Fixes made in our own check while doing this:**
- Python's `urllib.robotparser` applies the first matching rule; RFC 9309 applies the longest. Under the first rule,
  openbait.com `/api/mcp` would look allowed; it is disallowed.
- HISTOR had no four-field digest for fractional schemas before 31 Oct 16:42Z. Such sides are compared on the
  members kept beside the digest only, never read as "no tools".

## Correction from ScraperWatch, 2026-11-02

ScraperWatch wrote on 2026-11-02 (Wren, ops@scraperwatch.com) that it had not skipped every URL robots.txt
disallows: Python's first-match parser read "Allow: /" before a narrower Disallow as open, so from 30 Oct to
1 Nov it read about 250 panel endpoints that disallow the path. It removed those reads and their change
records; its 31 Oct and 1 Nov diffs now have 47 and 66 records instead of 57 and 77. The figures above stay as
they were: they describe the log as first fetched (`changes.json`, sha256 `41190f42…`).

The log after the removal is in `correction-2026-11-02/` (`changes.json`, sha256 `b8b316e9…`, fetched
~04:09Z). `recount.py` keeps our verdicts for the records it still has (`recount.txt`):

| | First fetch | After the removal |
|---|---:|---:|
| ScraperWatch records, 31 Oct + 1 Nov | 134 | 113 |
| Tool-change records | 98 | 81 |
| Same change in HISTOR, path by path | 64 | 53 |
| HISTOR has no definitions in the window | 25 | 20 |
| Server `instructions` only | 5 | 4 |
| Not seen as a change in HISTOR | 4 | 4 |
| Field items seen in the matches | 738 | 624 |
| Status transitions | 36 | 32 |

The removal took 17 tool-change and 4 status records on 17 endpoints; none of the four changes HISTOR did not
see was among them, and the handshake finding above is unchanged. HISTOR itself read 11 of the removed changes:
its crawler does not consult robots.txt.

The automatic cross-check was rerun the same morning on the corrected log, which now has a third day
(2 Nov): https://histor.modelmarket.dev/datasets/peers/scraperwatch/2026-11-02/ (`latest/` points there;
the 2026-11-01 run stays as it was). On theagentsbay.com, which that run lists as a likely miss on their side
for 2 Nov: its robots.txt answered ScraperWatch with HTTP 530 that morning, and they read a 5xx as disallowed.
