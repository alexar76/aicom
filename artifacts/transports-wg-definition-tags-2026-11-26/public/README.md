# What MCP tool-list changes look like (HISTOR snapshot of 23 November 2026)

Counts made for the MCP Transports Working Group's "Definition Tags" draft
(modelcontextprotocol/transports-wg, pull request 57), which leaves open which fields a tag covers and whether a tag
identifies a whole list or one tool. They are taken from HISTOR's public snapshot of 2026-11-23
(https://histor.modelmarket.dev/datasets/2026-11-23/), which holds every change HISTOR recorded on the servers of
the official MCP registry that it could read without credentials.

Published at https://histor.modelmarket.dev/datasets/tool-list-change-shapes-2026-11-26/. License: CC BY 4.0.

## Numbers

**Changes to name, description, inputSchema or outputSchema** (`results/change-shapes.json`, from `changes.jsonl.gz`,
2026-09-24T10:53:44Z to 2026-11-23T07:20:04Z): 177,296 changes on 21,458 servers.

- One publisher (one registrable domain) accounts for 96,475 of them (54.4%). Its tool descriptions carry a running
  total, so every tool list on about 1,850 registry entries changes when the total moves.
- The other 80,821 changes, on 19,601 servers:

| | changes | share |
|---|---:|---:|
| touched exactly one tool | 35,544 | 44.0% |
| touched two to five tools | 27,450 | 34.0% |
| touched six or more tools | 17,827 | 22.1% |
| same tool names, definitions changed | 58,604 | 72.5% |
| a tool was added or removed | 22,217 | 27.5% |
| only `description` changed | 20,074 | 24.8% |
| only `inputSchema` changed | 17,574 | 21.7% |
| `description` and `inputSchema` changed | 12,546 | 15.5% |

- 3,221 changes on 463 servers returned a server to a tool list it had served before. The median time away was
  1.5 hours; 1,178 came back within one hour and 2,786 within a day.

**Changes to other members of a tool** (`results/extras-shapes.json`, from `extras_changes.jsonl.gz`,
2026-10-23T18:22:44Z to 2026-11-23T07:20:04Z): 294,062 recorded changes on 9,488 servers. In 181,519 of them the four
members above did not change in the same read:

| what changed, alone | reads | servers |
|---|---:|---:|
| a vendor member `version` on each tool (one publisher) | 175,539 | 1,878 |
| a tool's `_meta` | 4,629 | 354 |
| annotations | 711 | 654 |
| annotations and `title` | 222 | 188 |
| `title` | 163 | 159 |

3,273 of the 4,629 `_meta`-only reads are on one host.

## Recount

Python 3.9 or newer, standard library only. The two change files are about 250 MB together.

    S=https://histor.modelmarket.dev/datasets/2026-11-23
    for f in changes.jsonl.gz extras_changes.jsonl.gz servers.jsonl.gz; do curl -fsSLO --retry 3 $S/$f; done
    curl -fsSLO https://publicsuffix.org/list/public_suffix_list.dat
    python3 scripts/change_shapes.py changes.jsonl.gz servers.jsonl.gz public_suffix_list.dat
    python3 scripts/extras_shapes.py extras_changes.jsonl.gz changes.jsonl.gz servers.jsonl.gz public_suffix_list.dat

## Limits

- One reader, without credentials: tool lists that differ per user or per organisation are not seen.
- A change is recorded when two consecutive reads of a server differ. Remote servers are read every six hours, and
  30 minutes after a change; packages once per published version. A change made and undone between two reads is not seen.
- Publishers are grouped by registrable domain (Public Suffix List); each npm or PyPI package counts as its own.
- Members other than the four are recorded since 2026-10-23.
- "Returned to an earlier list" compares digests of the four members over the whole list, within one server's history.
