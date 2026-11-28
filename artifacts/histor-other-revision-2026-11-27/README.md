# HISTOR keeps what a server lists after initialize beside the log — LIVE 2026-11-27 10:52Z

**Why.** Cross-check with the MCP Transparency Log (../histor-peer-mtl-2026-11-27/): a server that answers MCP
2026-07-28 and the handshake can list other definitions in each. HISTOR reads in the newest revision, so the log
holds the 2026-07-28 reading, and a handshake client asking `/api/v1/check` about such a server was told
`different`, "differs from every set HISTOR has observed" (checked on stackerscan). 4 of 277 sampled servers list
differently. Owner, 27.11: «Да, делай».

## Change (main bd0e37996)

- `McpReader.list_tools(url, handshake_only=True)`: opens with `initialize`, skips `server/discover`.
- Crawl: for a remote server just read in 2026-07-28, one more read-only read that opens with `initialize`, when
  its list changed or the stored reading is older than `HISTOR_REVISION_REREAD_DAYS` (7); at most
  `HISTOR_REVISION_READS_PER_DAY` (1500; 0 = off); same reader, robots rules and per-host limit. Stored in
  `revision_readings` (migration 027), one row per target, beside the log: no observation, no label.
- `/check`: `same-other-revision` when the client's set is that reading; `otherRevision` whenever the two lists
  differ; the `different` note says when HISTOR has no handshake reading of a 2026-07-28 server.
- WARDEN: the answer is in the type and the docs (no finding; unreleased). Tools service: in the output schema's
  enum (not deployed).

Tests: HISTOR suite 1727 passed on SQLite; with a throw-away local PostgreSQL 18 as the second backend 2067 passed,
8 skipped (production is PostgreSQL 16). HISTOR's reader with `handshake_only` reproduced both digests on
stackerscan and runescape-wiki from the Mac.

## Rollout (HISTOR host `/root/histor-other-revision-20261127`, kit in `kit/`)

Before: production ran `sha256:feabed44…`; the tag `latest` pointed to `sha256:745fac7b…` (the same image plus the
peer-check modules of this morning; tagged `histor-histor:pre-other-revision-20261127`); the six files in it and
in `/opt/histor/histor` were main's before this change; database at migration 26; no crawl running, alerts quiet.

- `build.sh`: `histor-histor:other-revision-20261127` = `sha256:9414eb56dd1474d0020d90776737a15906b6ab304d7d3eab7c214f4bf358fa94`,
  FROM the `latest` of the moment plus the six files; `smoke.py` inside it with no network (migration 27 on a fresh
  store, the store's three calls, the reader's parameter).
- `switch.sh`, 10:51:38Z start, 10:52:03Z healthy on the new image, 10:52:37Z SWITCH-OK: eight routes 200,
  migration 27 applied, reader and check carry the change, vendored WARDEN still 0.39.0; `/opt/histor/histor`
  updated to the same six files (previous ones in `opt-prev/`).
- MOMUS (admin-vps): image copied there, `skopos-warden-quality rebind sha256:9414eb56…` → `live-image.json`
  names it, build digest `18221b00…` unchanged.

Rollback: on the HISTOR host `/root/histor-other-revision-20261127/switch.sh rollback` (drops `revision_readings`
and the row of migration 27 first, because the old image refuses a database with a migration it does not know;
restores `/opt/histor/histor`; puts `latest` back on `745fac7b…`), then on admin-vps
`skopos-warden-quality rebind sha256:feabed44d9420c88a93b9aa89292f438372ebe82f51318a98091d082033574b7`.

## After (server UTC)

- 10:54:10Z: 70 handshake readings stored by the running crawl in two minutes, 69 `ok`, one `http-429`; no error in
  the application's log.
- 10:54:43Z: `histor reobserve` of stackerscan and runescape-wiki (the operator's command, one throw-away
  container): both got their reading, 2025-06-18, 6 and 14 tools, digests equal to this morning's handshake reads.
- From outside: `/api/v1/check` with stackerscan's handshake digest → `same-other-revision`, signed, note names the
  protocol and the day; with its 2026-07-28 digest → `same` (and `otherRevision` shown); with an unknown digest →
  `different`. The same for runescape-wiki's handshake digest.

At about 35 second readings a minute the day's 1500 are used within the hour; the roughly 7,000 servers on
2026-07-28 get theirs over about five days, then only changed lists and week-old readings are read again.

## Not done

- WARDEN and the tools service carry only the name of the new answer; neither is released or deployed with it.
  Released WARDENs print the answer and report no finding.
- HISTOR's package version is still 0.12.0 with an Unreleased section; the tree already differed from PyPI's 0.12.0.
