# HISTOR reads MCP server cards in production (2026-11-02)

Code `706b71bb7` (`histor/histor/cards.py`, migration 020; HISTOR CHANGELOG, Unreleased; `histor/docs/api.md`,
"Server cards"). The owner said "Yes, build it", then "Yes, roll it out" after the auto-mode classifier had stopped
the first attempt.

## Rollout

`histor_cards_overlay.sh` on admin-vps, 06:57:51–06:58:24Z (`rollout.log`):
- **Base.** `aicom-security:histor-histor-1-cd-20261102` = `e3aa16e9ecea`, built FROM the running `rb-20261102`
  (`d2f3b3dcea1e`).
- **Pre-checks.** All 13 replaced files were checked equal to `main` before `706b71bb7` in the running container.
- **Inside the image.** The MOMUS gate passed (run `20261102T042600`, build `bcfc888d…`, unchanged), and `smoke.py`
  passed.
- **Switch.** Compose moved to the new image and the service came up healthy, applying migration 020.
- **After.** The host tree was updated, the MOMUS binding moved to `e3aa16e9ecea`, and the crawl was restarted.
- **Rollback.** At the top of the script.

## The first pass (the scheduler's hourly declarations thread, done 08:01:55Z)

`server cards read: {'checked': 3000, 'urls': 5197, 'declared': 157, 'withdrawn': 0, ...}`

| Status | Endpoints |
|---|---:|
| `absent`: no card at an allowed path | 1,649 |
| `no-tools`: a card, without a complete tool list | 481 |
| `robots`: every card path disallowed | 302 |
| `ambiguous`: host-wide card naming no endpoint, several endpoints on the host | 237 |
| `declared`: a full tool list, now a declared set with `source: "card"` | 157 |
| `error`: the read failed (nothing withdrawn) | 122 |
| `other-endpoint`: the card names another endpoint | 52 |

How the 157 declared cards compare:
- 65 equal what HISTOR observes at the server;
- 42 differ from it;
- 50 servers have no observation of HISTOR's at all;
- 8 are on servers HISTOR no longer reads because of robots.txt.

No errors in the service log.

## Checked live

- **`https://briefme.us/mcp`** (`/s/03923a512abfa515`).
  - robots.txt disallows `/mcp` to HISTOR, so the status is `robots-disallowed`. The card at
    `/.well-known/mcp/server-card.json` declares 12 tools; its digest `sha256-9E0HQ+81w…` equals the last set
    HISTOR served.
  - `POST /api/v1/check` returns `target.serverCard` with that URL and digest.
  - The page shows the robots.txt note, "Карточка сервера: … · перечисляет 12 инструментов" and the declared set
    "HISTOR тоже наблюдал · … · в карточке сервера".
- **`https://app.hollyhr.com/api/mcp`.** HISTOR could not read it (`protocol`). The card is HISTOR's first
  description of it: 12 tools (`call_api_operation`, `commit_api_write`, …).

The other ~30,000 remote endpoints follow at 3,000 per hourly pass. After that a card is read again daily, or
weekly where none was found.
