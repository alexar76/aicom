# HISTOR: signed publisher statements + /api/v1/fingerprints on prod (scheduled 2026-11-20 after the crawl)

Owner 2026-11-19: «Да, делай» (read the publisher's signed statement), «прочитай» (the format's repository), «сделай»
(keep the extras digest, key id and dates: migration), «HISTOR как база для detectToolDrift — делай», «хистор после
исправлений выкатишь». Code: aicom main + Gitea 50cc9e686.

- Image `histor-histor:signed-fingerprints-20261119` =
  sha256:d81ba087c9b3f99749458be8bf1f2c8e12b9dce62f3fc364c5ef5afb8eebd524, FROM the live `warden-0.31.0-prod`
  (sha256:2604a2f6a4e005fd0268ac2ac047e662e70409bb16f7f804d842ed98c73e5a76), see `Dockerfile`. Compared file by file:
  the two images differ in exactly 16 files (13 changed, 3 new; `ctx.sha256`). `crawler.py`, `declared.py`,
  `store.py`, `registry.py`, `migrations.py` are main's (the image's equalled main before the change); `app.py`,
  `check.py`, `desk.js` and the five i18n files are the image's own with only this change applied (checked: the
  change against the image equals the change in the repository). Loaded on admin-vps too (same id).
- Migration 025 (`declaration_urls.pointer`, `declaration_urls.statement`, both nullable) rehearsed 2026-11-19 on a
  throw-away Postgres 16 in a network with no way out (`rehearse.sh`, output in `rehearsal.log`): old image 0→24;
  new image →25, the new routes answer, the new store statements run on Postgres; the old image refuses 25
  ("database is at revisions [25] this build does not know"); after `rollback.sql` the old image accepts 24; the new
  image re-applies 25. The first rehearsal run failed at step 2 for a reason of its own (the key folder was a tmpfs,
  so every restart had new keys); with a volume, as in production, it passes.
- Scheduled, both transient one-shot timers (lost on reboot; then run the scripts by hand):
  - HISTOR host `histor-signed-fingerprints-switch.timer` 2026-11-20 03:30:00 UTC → `after-crawl.sh`: waits (5-min
    polls, until 10:00Z) for no open crawl run (the crawl started 2026-11-19T18:31:06Z), checks that the running image
    is still `warden-0.31.0-prod`, runs `switch.sh`, rolls back on failure, then logs the fingerprints route, health
    and, 15 min later, remote polling failures. Log `/root/histor-signed-fingerprints-20261119/after-crawl.log`.
  - admin-vps `histor-signed-fingerprints-rebind.timer` 03:45:00 UTC → `rebind-after.sh`: rebinds MOMUS only when
    runtime.json reports d81ba087 (10-min polls, until 11:00Z). Log `/root/histor-signed-fingerprints-20261119/rebind.log`.
    (`<histor-host>` and `@NEW_IMAGE_ID@` in the copy here are filled in on the host.)
- Rollback by hand: HISTOR host `bash /root/histor-signed-fingerprints-20261119/switch.sh rollback`, then admin-vps
  `skopos-warden-quality rebind sha256:2604a2f6a4e005fd0268ac2ac047e662e70409bb16f7f804d842ed98c73e5a76`.
- What appears when. `/api/v1/fingerprints` answers right after the switch. A signed statement is first read when a
  crawl next reads the registry (the crawl that starts around 18:30 UTC on 2026-11-20), then hourly; until then
  `com.rtlpdf/arabic-pdf` shows no declared set.
- Not in this image: main's newer landing (journey, Watch UI). The server page gets only the label for the new source.

Result (read 2026-11-20 07:02Z, host clocks):

- The crawl ended 05:38:28Z. 05:40:20Z the switch started; 05:40:57Z HISTOR healthy on `sha256:d81ba087…`, schema 25;
  `SWITCH-OK`. 05:41:58Z the fingerprints route 200, health 200. 05:56:59Z: remote polling failures since the switch 0,
  errors in the log 0. No rollback.
- admin-vps: `REBIND-OK` 05:45:03Z.
- From outside, 07:02Z: `/health` 200, `/api/v1/fingerprints?profile=ai-sdk&endpoint=https://mcp.deepwiki.com/mcp`
  200 with `histor.fingerprints/v1`.
- 05:57:45Z production moved on to `histor-histor:warden-0.32.0-prod` (`sha256:7fa51dbf…` = this image plus WARDEN
  0.32.0; `warden/docs/evidence/warden-release-0.32.0-2026-11-20/`). The rollback of this release now starts with that
  folder's rollback.
- Not yet seen: a signed statement read by a crawl. `declaration_urls` had no pointer or statement at 07:02Z; the
  next crawl starts about 18:30Z.