# Server cards of the sites that keep HISTOR off their MCP path (2026-11-02)

Since 05:40Z HISTOR follows robots.txt and no longer reads 4,708 registry-listed endpoints (survey of the same
morning). Some of these sites allow a server card while disallowing the MCP path; `signupsheet.page`, for example,
has `Disallow: /mcp` and `Allow: /mcp/server-card`. This counts what such cards could give back without touching a
disallowed path.

## How

- **`cards_survey.py`** ran on admin-vps as a systemd unit, 2026-11-02, about 05:45–05:50Z, from the robots survey
  data.
  - **Hosts:** the 4,359 hosts with a disallowed endpoint.
  - **Paths asked:** `/.well-known/mcp/server-card.json`, `/.well-known/mcp.json`, `/.well-known/mcp`,
    `<endpoint path>/server-card`, and every literal Allow path naming a server card or `/.well-known/mcp`.
  - **Rules:** a path was asked only when the host's own robots.txt allows it to `histor`. That gave 9,253 URLs,
    one GET each.
  - **Result:** `cards.jsonl.gz` (sha256 `7321c9b9…`), kept on admin-vps in
    `/root/histor-server-cards-20261102/` and not in git. It holds the sites' own texts.
- **`compare_cards.py`** checked each card against HISTOR's own observation.
  - **Which cards:** every endpoint on a host whose card lists every tool with a name and an `inputSchema`.
  - **How:** one `POST /api/v1/check` with the card's tools and no `contribute`, so HISTOR computes the digest
    exactly as its log does.
  - **Result:** `compare.jsonl`.

## Results

| | Count |
|---|---:|
| Allowed candidate URLs asked | 9,253 |
| JSON answers | 1,448 |
| Card-like documents (serverInfo or a tools member) | 832 on 680 hosts |
| … with a tool list | 706 on 582 hosts |
| … where every tool has a name and an inputSchema | 319 on 280 hosts |
| Disallowed endpoints on those hosts, checked | 281 |

Where the card stands against HISTOR (281 endpoints):

| HISTOR's answer for the card's tools | Endpoints |
|---|---:|
| `same`: the tool set HISTOR currently holds | 84 |
| `previously-observed`: a set HISTOR saw before | 4 |
| `different`: not what HISTOR observed | 49 |
| `not-observed`: HISTOR never read this server | 144 |

- **Unread servers.** Of the 144 never read, 129 answer HISTOR with 401: they need a key for `tools/list`, yet
  their card lists the tools publicly.
- **Servers HISTOR had read (137).** The card equals the served set in 84 (61%), an older one in 4, and something
  else in 49 (36%).

## What it means

- **Cards are the publisher's word, not an observation.** One in three disagrees with what the same server served.
  HISTOR already has that category ("declared", `histor/declared.py`: digests from the registry entry or the
  publisher's own domain, never counted as an observation, never labelled).
- **What reading allowed cards would give back:**
  - a publisher-declared tool list for 281 of the 4,708 now-unread endpoints;
  - a first public description for 144 servers HISTOR has never been able to read, 129 of them behind a login;
  - for the servers HISTOR does read, a check of the card against the served set.
- **This is not built.** Building it means fetching allowed card paths daily, digesting their tools, recording them
  as declared sets with the URL and date, and showing "the card says / the server serves" side by side.

The MCP Server Card format merged on 2026-10-06 (SEP-2127) leaves tool listings out on purpose. The cards here that
carry tools follow earlier drafts or add them on their own, so this count may shrink as sites follow the spec.
