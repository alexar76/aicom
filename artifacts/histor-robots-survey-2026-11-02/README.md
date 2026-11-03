# How many of HISTOR's remote MCP endpoints does their own robots.txt disallow? (2026-11-02)

HISTOR's crawler does not read robots.txt. ScraperWatch, the peer HISTOR cross-checks, does, and on
2026-11-02 it removed the reads its first-match parser had let through. This counts what HISTOR would
stop reading if it followed RFC 9309.

## How

- **Endpoints:** every listed remote endpoint in HISTOR's public snapshot of 2026-10-26
  (`/datasets/2026-10-26/servers.jsonl.gz`), without templated URLs. That is 33,520 endpoints on
  24,282 hosts. `endpoints.tsv` (id, endpoint, lastStatus, changes, observations; sha256 `4a9adefd…`)
  is regenerated from that file.
- **Fetch:** `robots_survey.py fetch`, run on admin-vps (HISTOR's address) as a systemd unit,
  2026-11-02 04:17–04:23Z.
  - One GET of `https://<host>/robots.txt` per host, 10 s timeout, at most 512 KiB, 32 at a time.
  - User-Agent `histor-robots-survey/1 (+https://histor.modelmarket.dev/#crawler; …)`.
  - A host resolving to a non-public address was not asked, and redirects were followed only to
    public hosts.
  - Result kept on admin-vps: `/root/histor-robots-survey-20261102/hosts.jsonl.gz` (sha256 `d6dda788…`).
- **Match:** `robots_survey.py match`, the rule of `histor/peer_xcheck.py`:
  - the group naming `histor`, else `*`;
  - the longest matching rule wins, Allow wins a tie;
  - `*` and a trailing `$` are wildcards;
  - a 4xx means no robots.txt (everything allowed);
  - a 5xx or no answer is counted on its own, because RFC 9309 says to assume complete disallow there.

## Hosts

| robots.txt | Hosts |
|---|---:|
| served (200) | 16,393 |
| 4xx (none) | 6,447 |
| 5xx | 504 |
| no answer (timeout, TLS, refused) | 715 |
| not asked (non-public address or no DNS) | 217 |
| over 512 KiB | 6 |

No robots.txt names `histor`.

## Endpoints

| | Endpoints | Share |
|---|---:|---:|
| Allowed by a robots.txt | 19,218 | 57.3% |
| No robots.txt (4xx) | 8,059 | 24.0% |
| **Disallowed** | **4,708** on 4,359 hosts | **14.0%** |
| robots.txt 5xx or no answer (RFC 9309: assume disallow) | 1,277 | 3.8% |
| Not asked / too large | 258 | 0.8% |

What the disallowed ones are, by the rule that decides (`match.json` and the split below):

| The deciding Disallow | Endpoints | Hosts | HISTOR reads them now | Changes HISTOR recorded |
|---|---:|---:|---:|---:|
| The MCP path itself (`/mcp`, `/mcp/`, `/sse`, `…/mcp`) | 1,489 | 1,263 | 989 | 1,666 |
| An API prefix (`/api/`, `/api`, `/v1/`) | 1,911 | 1,830 | 943 | 1,514 |
| The whole site (`/`) | 1,279 | 1,241 | 271 | 504 |
| Another prefix | 29 | 28 | 21 | 28 |
| *(5xx or no answer)* | *1,277* | *1,219* | *106* | *181* |

Against all remote endpoints: HISTOR reads 19,649 successfully and has recorded 27,034 changes on
9,122 of them. Following robots.txt would end:
- the reads of 2,224 endpoints it reads today (11.3%);
- the 3,712 changes recorded so far on them (13.7%).

Treating a 5xx as a ban, as RFC 9309 asks, adds 106 endpoints it reads now.

Most blocks are not about MCP. `/api/` and `/` are the usual rules aimed at search crawlers, and an MCP
endpoint often sits under them. 1,489 endpoints (4.4%) disallow the MCP path itself, for example:
- `Disallow: /mcp`;
- `a2awire.com` with `Disallow: /mcp/` on 120 endpoints;
- `api.ufcalendar.com`, whose file says its MCP server is "POST only, nothing to crawl".

## Also found

HISTOR's public FAQ ("I run an MCP server. What does HISTOR send it…", `#crawler`, five languages) is out
of date:
- **Frequency.** It says "once a day". Production reads remote endpoints every 6 h
  (`HISTOR_REMOTE_INTERVAL_S=21600`) and every 30 min after a change (`HISTOR_REMOTE_CHANGED_INTERVAL_S=1800`).
- **Requests.** It lists `initialize`, but since 2026-10-29 HISTOR opens with `server/discover`.
- **robots.txt.** It does not say that robots.txt is not read; the only opt-out is an issue on the repository.

Snapshot caveat: the endpoint list is a week old, and robots.txt was read once on 2026-11-02.
