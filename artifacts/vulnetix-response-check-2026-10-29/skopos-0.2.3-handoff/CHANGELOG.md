# Changelog

All notable changes to SKOPOS (self-hosted nginx analytics & AI security) are documented here.


## [0.2.3] — 2026-10-29

### Security
- **Dashboard login addresses could still be forged on Streamlit 1.66.1** (remaining exposure in
  Vulnetix GCVE-110-PYPI-2026-021896). The dashboard read the old Tornado session client's
  `request.remote_ip`, which the current Starlette session client does not expose. With no peer
  found, the dashboard accepted `X-Real-IP` / `X-Forwarded-For`
  without verifying `SKOPOS_TRUSTED_PROXIES`. A caller reaching the dashboard directly, or through
  a proxy that preserved those headers, could choose a per-address login bucket and claim a known
  address's pacing exemption. The dashboard now reads the actual socket peer from Uvicorn's
  transport and applies the configured proxy allowlist. It does not use Streamlit's context IP:
  Uvicorn may already have rewritten that value from forwarded headers. This also preserves an
  empty `SKOPOS_TRUSTED_PROXIES` or `SKOPOS_TRUSTED_PROXY_HOPS=0`. An unavailable or invalid peer uses the shared
  `unknown` bucket and never grants authority to address headers. The existing signed-session-cookie
  recovery, per-address lockout and bounded all-addresses login delay remain in place.


## [0.2.2] — 2026-10-28

### Security
- **The all-addresses login budget let anyone lock the operator out** (Vulnetix GCVE-110-VULN-PYPI-2026-000644,
  new in 0.2.1). Over `SKOPOS_LOGIN_GLOBAL_MAX_ATTEMPTS` logins now slow down instead of stopping: each
  further failure makes the next try from a new address wait longer (2, 4, 8 … seconds, at most a minute),
  and an address that logged in successfully within `SKOPOS_LOGIN_KNOWN_DAYS` (default 30) never waits.
  Each submitted attempt takes one bounded delay before its password is checked; failures elsewhere
  cannot move that attempt's deadline or hide the login form. The per-address lockout is rechecked
  after the delay, so concurrent guesses from the same address still exhaust its own budget.
- **Remediation `git push` skipped the host-key check for single-label remotes** (Vulnetix
  GCVE-110-VULN-PYPI-2026-000639). A container name resolves on whatever network the container shares.
  Every SSH remote is now pinned on first use and refused if its key changes; only a loopback Gitea may
  skip the check, and only with `SKOPOS_GIT_SKIP_HOST_KEY_LOOPBACK=1`. Keep Gitea's SSH host keys in its
  data volume and a recreate keeps them.
- **Proxy headers were taken from any private peer** (the class of Vulnetix GCVE-110-VULN-PYPI-2026-000636).
  `X-Real-IP` / `X-Forwarded-For` now count only from `SKOPOS_TRUSTED_PROXIES` (addresses, CIDRs, host names,
  `gateway`; loopback by default). The compose file trusts `gateway`, the host's nginx.

## [0.2.1] — 2026-10-25

### Security
- **Login lockout could be sidestepped where SKOPOS is reached without our proxy** (Vulnetix
  GCVE-110-PYPI-2026-021896, CWE-307). The lockout key took `X-Real-IP` from any caller, so a client
  that reached Streamlit directly put each guess under a new address. The key is now the websocket's
  own peer, and proxy headers count only when that peer is the local proxy; every failed login also
  counts against an all-addresses budget (`SKOPOS_LOGIN_GLOBAL_MAX_ATTEMPTS`, default 30 per 15 min),
  which bounds guessing whatever the key. SSH host keys are verified by default since 0.1.5
  (`RejectPolicy` with SKOPOS's own known_hosts); 0.1.0–0.1.4 accepted any key.
- **Remediation `git push` accepted any SSH host key** (CWE-295, the class of the record above). The
  push ran with `StrictHostKeyChecking=no`, so whoever could answer for the git host on the network
  received the commit and the deploy key's signature. It now keeps the first key it sees in
  `~/.skopos/known_hosts` (`SKOPOS_KNOWN_HOSTS`) and refuses a changed one; only a remote on this
  machine or a single-label container name keeps the old behaviour.

## [0.1.4] — 2026-07-20

### Added
- **People (est.) KPI** — GA-comparable visitor estimate: unique IPs that fetched a page document AND its assets from a non-datacenter network. Replay fleets (identical-UA proxy botnets requesting only APIs/RSC payloads) and scanners (pages without assets) are excluded — UA filters alone cannot catch bots with perfect browser UAs
- **Hide datacenter IPs** filter (4th checkbox) — offline IP→ASN enrichment via the free iptoasn.com dump (`scripts/install_iptoasn.sh`, no license key); new `asn`/`asn_org` columns, `skoposctl backfill-asn` for existing rows
- **Data coverage notice** — when the selected period extends beyond ingested logs (e.g. 30d picker over 6 days of logs), the Analytics header now says where data actually starts; explains most "Skopos vs GA" mismatch

### Fixed
- Hide bots left ~90% non-human traffic in "unique IPs": a 72-IP residential-proxy fleet with identical `X11 Chrome/149` UA and Tencent-cloud fake-iPhone probes passed all UA heuristics

## [Unreleased]

### Added
- **Security Report** tab — consolidated AI remediation report with Markdown export
- **Scan History** page — score timeline, trends, scan comparison
- **Auto security scan** — configurable interval in Settings (default 60 min)
- **Voice input** for sidebar AI agent (Web Speech API)
- **Fullscreen mode** for 3D threat map and traffic globe
- Cyberpunk 3D threat map — server rack, textured globe, aggregated alerts
- Getting-started onboarding checklists (Analytics & Security)
- **Quick Start wizard** — guided setup page (server, SSH, collect, scan)
- Sidebar product tagline and password-protected dashboard warning
- MIT LICENSE, updated docs and README for discoverability

### Changed
- Streamlit page URLs without emoji in filenames (`pages/1_Security.py`, etc.)
- Browser tab titles: `SKOPOS — …` on all pages
- README aligned with OpenRouter default in `agent.yaml`
- RU/ES locale fixes for Settings strings

### Fixed
- Duplicate docker disk findings on 3D map and in audit
- Fullscreen chart CSS (`Theme.app_bg`)
- Scan history query layer for AI agent context
- Security hardening: SSH log fetch quoting, auto-scan import bug, auth lockout/session TTL, LLM auth-log redaction, custom SSH commands gated, config path traversal guard, alert XSS escape, GeoIP HTTPS, DB permissions, CDN-free voice component

## [0.1.3] — 2026-07-20

### Fixed
- **Hide bots / Hide service** still left mass scanner + ecosystem noise in KPIs (websiphon, libredtail, l9explore, empty UA, AIMarketHub, python-requests, …)
- Expanded bot/scanner heuristics and service UA/path lists; empty `-` UA treated as bot

## [0.1.2] — 2026-07-20

### Fixed
- **Hide bots** left crawlers visible when `user_agents` set `is_bot=False` (Applebot, 360Spider, OAI-SearchBot, …)
- Analytics SQL filter now drops heuristic bot UA/browser matches, not only `ua_is_bot=1`
- UA ingest + backfill re-flag false-negative bot rows

## [0.1.1] — 2026-07-20

### Changed
- Analytics KPIs/charts computed via SQL aggregates over the full period (no row sampling / newest-N cap)
- Period filter uses `ts_utc` + partial file-log index; journal still ORDER BY + LIMIT
- Running status pill cleared below the Filters card border

### Fixed
- 24h vs 7d geo charts identical under high traffic
- Duplicate «Unique IPs» column crashing the country summary table

## [0.1.0] — 2026-07

- Initial release: nginx SSH analytics, Security Center, AI agent, i18n (EN/RU/ES)
