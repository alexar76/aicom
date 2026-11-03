# MCP protocol versions and server versions on remote MCP servers (1 Nov 2026)

Two questions about the remote MCP servers in the official MCP registry, answered from HISTOR's records:

1. Which MCP protocol version does each server speak? Since revision 2026-07-28, MCP has two eras that open
   differently. The new one carries metadata on every request; the older ones (2025-11-25 and earlier) start with
   an `initialize` handshake.
2. Does `serverInfo.version` change when a server's tool definitions change?

The files also cover one episode that shows why the first question matters. From 29 October HISTOR's own reader
tried the 2026-07-28 era first and did not fall back to `initialize` where the MCP specification says to. It
stopped reading servers it had read before, until the fix went live on 1 November at 08:44:57Z.

Published at https://histor.modelmarket.dev/datasets/mcp-protocol-eras-2026-11-01/. License: CC BY 4.0.

## Numbers

All numbers are recomputed from the files by `scripts/summarize.py`; its output is
[results/summary.json](results/summary.json).

**Protocol versions** (`results/remote-protocols.csv.gz`). There are 21,474 listed remote servers (streamable-http
or sse) with at least one successful read between 25 October and 1 November 09:15:00Z. Their latest successful read
used:

| protocol version | servers |
|---|---:|
| 2026-07-28 | 4,097 |
| 2025-06-18 | 13,744 |
| 2025-03-26 | 2,853 |
| 2024-11-05 | 650 |
| 2025-11-25 | 126 |
| other / none recorded | 4 |

So 4,097 servers (19%) answered in the 2026-07-28 era and 17,375 needed `initialize`.

**Server versions** (`results/same-version-changes.csv.gz`). There are 21,401 recorded changes to remote servers'
tool definitions where both runs recorded a `serverInfo.version`. In 17,401 of them (81.3%), on 6,802 servers, the
version was the same before and after. These are the remote changes of HISTOR's 2026-10-20 snapshot
(https://doi.org/10.5281/zenodo.23512760); `change_id` joins to the `id` in its `changes.jsonl.gz`.

**Servers left unread** (`results/unread-since-2026-10-30.csv.gz`). 2,195 remote servers were read successfully on
28 October, then had no successful read from 30 October until the fix. Their last failure before the fix:

| last failure | servers |
|---|---:|
| reader refused to fall back (the four `protocol` details below) | 1,250 |
| `http-401` / `http-403` | 746 |
| other: 5xx, timeouts, 404, 402, other `protocol` details | 199 |

The four reader refusals:

| detail | servers |
|---|---:|
| HTTP error did not match our request id | 789 |
| modern discovery did not advertise the requested version | 304 |
| malformed JSON-RPC error response | 120 |
| no mutually supported modern protocol version | 37 |

Most of the 401/403 were the same bug. Some servers ask for a token for every method except `initialize` and
`tools/list`, so the new-era request was refused; mcp.kaiku.tech, for example, reads fine with `initialize`. The
other 199 include servers that broke for their own reasons.

By the as-of time none of the 2,195 had been read again (`first_ok_after_fix` is empty). They come back as their
retry delays run out, the last by 2 November 08:41Z. The fix follows the Backward Compatibility rule of MCP
2026-07-28 Streamable HTTP: a first new-era request refused with a 4xx that carries no recognized new-era error means
a legacy server, so the client sends `initialize`.

## Files

- `results/remote-protocols.csv.gz` — one row per server:
  - `server_id`, `name`, `endpoint`, `transport`;
  - `last_ok_at`, `protocol_version` (what that read negotiated), `tool_count`;
  - `server_name`, `server_version` (`serverInfo` as reported).
- `results/same-version-changes.csv.gz` — one row per change:
  - `change_id`, `server_id`, `endpoint`, `observed_at`;
  - `from_server_version`, `to_server_version`, `same_version` (`t`/`f`, exact string comparison).
- `results/unread-since-2026-10-30.csv.gz` — one row per server:
  - `server_id`, `name`, `endpoint`;
  - `failed_status`, `failed_detail`, `failed_at`;
  - `first_ok_after_fix`, `protocol_after_fix`.
- `scripts/*.sql` — the read-only queries against HISTOR's database that wrote the three files.
  `same-version-ids.txt` holds the 21,401 change ids.
- `scripts/summarize.py` — the numbers above. Usage: `python3 scripts/summarize.py results/`.
- `SHA256SUMS`.

## What the data does not say

- **`protocol_version` is what a server negotiated with HISTOR's reader, not every version it supports.**
  - Before 29 October that reader opened only with `initialize`. So a server that speaks both eras and was last read
    before then is listed with a legacy version; that applies to 165 servers.
  - From 29 October the reader tried 2026-07-28 first.
- **Only servers with a successful read are in `remote-protocols`.** Servers that always require authentication, or
  were down for the whole window, are not.
- **`serverInfo.version` is what the server put in `initialize`.** Several deployments can report one string, and
  the comparison is exact. For the registry's own version numbers the picture is similar: 81.4% unchanged, measured
  separately on the same snapshot.

## Cite

Artamokhov, A. (2026). MCP protocol versions and server versions on remote MCP servers, 1 Nov 2026. HISTOR.
https://histor.modelmarket.dev/datasets/mcp-protocol-eras-2026-11-01/
