# HISTOR: cards at /.well-known/mcp.json, 402 reasons and "Outside checks" in production (2026-11-02)

The owner said "Yes, roll it out" after these changes:
- `f6bb99cb5`: the mcp.json card path, migration 021, and the "Outside checks" section of the page;
- `7256435da`: a 402 says why (`pay-per-crawl` / `payment-required` / `http-402` with the server's message), a back-off
  of at least a day, and the page and `/check` notes.

## Rollout

`histor_overlay.sh` on admin-vps, 15:30:38–15:31:03Z (`rollout.log`):
- **Base.** `aicom-security:histor-histor-1-mj-20261102` = `aebbc1ff7fa0`, built FROM the running `cd-20261102`
  (`e3aa16e9ecea`). Its OS patches, baked env and WARDEN build are unchanged.
- **Pre-checks.** All 13 replaced files (5 Python, 8 landing) were checked equal to main before f6bb99cb5 in the running
  container. The staged files were taken from `git show 7256435da:`, not from a working tree. macOS `._*` files from
  the copy were deleted before the build.
- **Inside the image.** The MOMUS release gate passed (run `20261102T042600`, build `bcfc888d…`, unchanged), and
  `smoke.py` passed.
- **Switch.** Compose moved to the new image; health came back on postgresql at tree size 1,519,491. The host tree was
  updated and the MOMUS binding moved to `aebbc1ff7fa0`. No crawl was running, so none was restarted.
- **Rollback.** At the top of the script. Migration 021 stays: it only made rows due sooner.

## Checked live (15:32Z)

- **Migration 021.** The schema is at 21. All 13,516 `absent` and 2,087 `robots` card rows are due again. 24,000
  endpoints have been card-read so far, 1,221 with declared sets.
- **Page.** `/` has `id="checks"`; `/assets/i18n/ru.js` has the new strings; `/assets/desk.js` knows `pay-per-crawl`.
- **Log.** No errors.
- **402s.** The 133 `http-402` targets are reclassified as each is read again; back-off applies after the first new
  read. groundtruths is due 2026-11-03T03:32Z.
