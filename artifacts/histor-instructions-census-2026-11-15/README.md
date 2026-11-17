# Server-level `instructions` of remote MCP servers, 2026-11-15

Owner: «замерь instructions у серверов» (after MCP spec issue #3430, where a host-guidance proposal asks for a
server-level summary in the first-level prompt).

## What was read

- **Who:** remote (streamable HTTP) targets that HISTOR currently reads with status `ok`, no skip reason
  (opt-out, robots) and still listed: 21,362 endpoints on 14,359 hosts. At most 3 per host, chosen by
  `md5('census-20261115:' || id)`: 15,021 targets (`targets.jsonl` sha256 4805a29a…c08 on the HISTOR host).
  Packages (npm/PyPI over stdio) are not in it: their handshake runs in the sandbox.
- **How:** `histor/scripts/instructions_census.py` with HISTOR's own client (`McpReader`): the crawler's
  User-Agent, discover-then-initialize, the tools/list drain, the public-address guard and the robots.txt policy.
  The only addition is keeping the `instructions` member of the `server/discover` or `initialize` result.
  One host's endpoints were read one after another; 24 hosts at a time.
- **Where/when:** a throw-away container from `histor-histor:landing-scanner-20261115` on the HISTOR host,
  1 CPU, 18:57–19:46Z 2026-11-15 (server clock).
- **Raw:** `out.jsonl.gz` (sha256 d115195f4acd1c20d6c81d0543648795f8d5848f663932f8b1c84fc111f5c826): one row per
  target with status, era, protocol, tool count, the registry description and the instructions text.
  `report.txt` = `histor/scripts/instructions_census_report.py out.jsonl`.

## Results

Status: ok 14,876; http-429 54, robots-unreachable 33, timeout 25, other 33.

Per host (first ok entry per host; per entry is within 0.1 point):

| | Hosts | Send non-empty `instructions` | Median length (chars) | p90 |
|---|---|---|---|---|
| all | 14,230 | 10,812 (76.0 %) | 665 | 2,157 |
| 1–5 tools | 6,254 | 72.7 % | 479 | 1,277 |
| 6–15 tools | 5,438 | 78.5 % | 757 | 2,045 |
| 16–40 tools | 1,799 | 78.6 % | 1,150 | 4,100 |
| 41+ tools | 739 | 79.0 % | 1,272 | 6,126 |

- Longer than 100 characters (the registry's `server.json` description limit): 10,638 hosts (74.8 %).
- Era: legacy (initialize) 73.7 %, modern (server/discover, 2026-07-28) 82.5 %.
- Texts are per server: 10,588 distinct texts on 10,812 hosts; the largest shared text is one publisher's on 55
  hosts. Identical to the server's registry description: 1 host.
- Steering away from other tools, read by hand: 34 hosts (0.3 % of hosts with instructions; hf.co and
  huggingface.co are one publisher) tell the model to prefer their tools over web search, the client's built-in
  tools, or its own knowledge / training data. The filter is `ROUTING` in the report script; all 34 hits were read.
- `instructions` was always a string when present (no other types).

## Limits

- Servers HISTOR reads successfully today, so servers behind authentication (no tool list for an anonymous
  client) are not in it, and neither are packages.
- One read per target; a server may vary its text by client or time.
- "Routing" is a phrase filter plus reading; it counts explicit preference over other tools, not every
  instruction about when to use a server's own tools.

Once migration 024 is live, the crawler records `instructions` on every observation (remote reads at once,
packages with the next sandbox observer rollout), so later numbers come from the log rather than a one-off read.
