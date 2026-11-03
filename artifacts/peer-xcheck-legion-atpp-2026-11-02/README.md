# HISTOR against LEGION-tlog and ATPP, 2026-11-02

Two more public records of what MCP servers in the official registry advertise, found on 2026-11-02 in another
server's client classifier (taktekhq/lebanese-legislation lists the user agents `LEGION-tlog/1.0` and `atpp-scan/1.0`
beside HISTOR's). Owner: «Сверка с LEGION-tlog и ATPP - делай».

- **LEGION-tlog** (legion-api.com/tlog). A signed RFC 6962 log, 49,621 leaves on 22,246 servers since 2026-10-08.
  - Reads remote endpoints with `initialize` and `tools/list` and records a leaf only when the list changes.
  - Each leaf carries `per_tool_sha256`, SHA-256 over RFC 8785 of `{name, description, inputSchema}` (algo `/v2`).
  - Read through `https://tlog.legion-api.com/tlog/v0/servers/<registry name>`.
- **ATPP** (Redthread Security, trust.redthreadsec.com, github.com/bl014h/atpp). A daily signed in-toto claim per
  registry server.
  - `predicate.tools` = `{count, sha256}`; checks such as `tools-stable`.
  - Read through `https://trust.redthreadsec.com/v/mcp/<name>.json`. The daily manifest in the repository holds only
    claim hashes.

## Method

- **Sample.** A random 800 (seed 20261102) of the 22,322 registry names that have exactly one remote endpoint and a
  recorded tool set in HISTOR's public snapshot of 2026-11-02 (07:20:03Z): `sample.jsonl`.
- **HISTOR side.** Tool definitions from that snapshot (`toolsets.jsonl.gz`), extracted on the host from the public
  files (`extract_toolsets.py`), never from the live service. Every earlier set of the servers that differ came
  from `changes.jsonl.gz`.
- **LEGION side.** One request per name: `fetch_legion.py` at 3 at a time, then `retry_legion.py` one at a time 2 s
  apart, after 429 and 530 answers.
  - Fetched 2026-11-02 between about 12:30Z and 13:50Z; `latest_record` is LEGION's newest leaf.
- **ATPP side.** One request per name, one at a time (`fetch_atpp.py`). Every claim was `as_of` 2026-11-01.
- **Scripts.** `compare_legion.py`, `explain.py` (timing and HISTOR's live API for the differing servers), `classify.py`
  (does LEGION's list equal a set HISTOR held at some time), `compare_atpp.py`.
- **Inputs.** The raw answers are in `../research-data/legion-xcheck-2026-11-02` and `../research-data/atpp-2026-11-02`,
  outside git.

## LEGION

765 of the 800 names are in LEGION (35 answer 404).

| | Servers | Tools |
|---|---:|---:|
| Every tool identical, byte for byte, under LEGION's own per-tool rule | 698 (91.2%) | — |
| Tool hashes identical | — | 11,919 of 12,237 (97.4%) |
| Differ | 67 | 318 |

Why the 67 differ (`classified.json`, `explain.json`):

| Servers | Reason |
|---:|---|
| 56 | **One gateway publisher.** Its definitions change every few hours: HISTOR recorded two changes on each of these servers in the three hours before the snapshot, and LEGION's latest leaf is from 27 Oct to 2 Nov. 16 equal a set HISTOR held earlier; 40 equal no set HISTOR kept whole, but they are made of tool versions HISTOR also recorded. |
| 3 | **LEGION keeps an older list after HISTOR recorded later changes.** aiapplyd: LEGION 10-19, HISTOR changes from 10-24. forest-factory: 10-13 against 10-29. modevc: 10-18 against 10-22. LEGION's newest leaf equals the set HISTOR held before. |
| 3 | **Both see frequent changes; LEGION's latest equals HISTOR's previous set** (salesmap, bootyplease sideeye, rundata). Read cadence: LEGION cycles in 6 h, HISTOR reads changing servers every 30 min. |
| 3 | **HISTOR behind.** agentalog changed at 11:45Z, after the snapshot. aiskillstore: HISTOR's last read timed out. euroref: HISTOR got 403. In all three HISTOR's live API now equals LEGION. |
| 1 | **groundtruths: HISTOR is charged to read it.** The server answers HISTOR with HTTP 402 "Pay per crawl. $0.01 a page" (Cloudflare pay-per-crawl or x402); it recognises the word `crawler` in HISTOR's User-Agent. LEGION and ATPP read its 20 tools free; HISTOR's last read is from 23 Oct (17 tools). |
| 1 | **sagots.** 135 of 136 tools equal a version HISTOR recorded; one tool differs and was not explained. |

The snapshot has 131 remote endpoints whose last read was 402, on 112 hosts. Most are paid MCP servers that answer
402 to any unpaid call. How many are pay-per-crawl keyed on the user agent, like groundtruths, was not measured.

## ATPP

- **Claims.** 791 of the 800 names have a claim (9 answer 404); 715 carry a tool digest, 76 do not.
- **Digest reproduced.** HISTOR's entries reproduce ATPP's list digest for **647 of the 715 (90.5%)**.
  - The form: SHA-256 over the tools sorted by name, each `{name, description, inputSchema}`, serialised with Python's
    `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
  - It is **not RFC 8785.** On 9 of the 647, RFC 8785 gives a different digest because the schema holds a number such
    as `10.0` or `1e-06`, which Python keeps and JCS writes as `10` and `0.000001`. A verifier in JavaScript cannot
    reproduce those 9.
- **Same list digest as LEGION.** ATPP's digest equals LEGION's list digest (`tools_sha256`) on 645 servers.
- **The 68 that differ:**

  | Servers | Reason |
  |---:|---|
  | 56 | The same gateway publisher. |
  | 6 | Changed after ATPP's daily scan of 1 Nov. HISTOR and LEGION agree with each other. |
  | 4 | Frequent or missed changes, as for LEGION above. |
  | 1 | groundtruths (402 to HISTOR). |
  | 1 | readyapis: same count; not in LEGION; not explained. |

## What this says

- **Three independent readers agree.** On the servers all three read, they record the same definitions byte for
  byte for about nine in ten servers.
- **Almost every difference has a cause:**
  - one publisher that changes its definitions every few hours;
  - read times;
  - a reader that missed later changes;
  - a server that charges crawlers.
- **For HISTOR:**
  - a 402 should say why (pay per crawl, or a paid endpoint), as robots.txt does now;
  - two read failures (timeout, 403) were caught by another log.
- **For LEGION:** three servers where its newest leaf is older than changes HISTOR recorded.
- **For ATPP:** its digest depends on Python's number formatting.
