# HISTOR: the subregistry on prod (scheduled 2026-11-20, after the signed-fingerprints rollout)

Owner 2026-11-20: «Yes, deploy». Code: aicom main + Gitea 56b85fd35 (`histor/histor/subregistry.py`, migration 026).

- Image `histor-histor:subregistry-20261120` =
  sha256:e6ed85ce0cfebee35c3de3f74f16c36be35e450254bc90d765116d0e315db2e5, FROM `signed-fingerprints-20261119`
  (sha256:d81ba087…), see `Dockerfile`: five files (`ctx.sha256`). `config.py`, `service.py`, `migrations.py` and the
  new `subregistry.py` are main's (each of the first three equalled main in the base image before the change);
  `app.py` is the base image's own with only this change applied (the import and the mount; the diff against the
  image equals the diff in the repository). Built on the HISTOR host 2026-11-20 03:55Z; loaded on admin-vps (same id).
- Why not at once: at 03:51Z production still ran `warden-0.31.0-prod`, a crawl was open, and the
  signed-fingerprints rollout (`artifacts/histor-signed-fingerprints-rollout-2026-11-19`) was waiting for that crawl
  to end. This image is built on that one, so it goes after it.
- Migration 026 (a new table `registry_entries`, two indexes) rehearsed 2026-11-20 on a throw-away Postgres 16 in a
  network with no way out (`rehearse.sh`, output in `rehearsal.log`): base image 0→25; new image →26, routes absent
  with the subregistry off, present and empty with it on; the subregistry's statements on Postgres (paging 47
  entries, search with `%` and `_`, `latest`, `updated_since`, versions, deleted entries, the observed block, an
  entry with a lone surrogate and a NUL, marking unseen, dropping unlisted); the base image refuses 26; after
  `rollback.sql` it accepts 25; the new image re-applies 26. The first run of step 4 failed on the rehearsal's own
  scenario (it re-applied an old page that still named a superseded version latest); corrected and re-run.
- Scheduled, both transient units (lost on reboot; then run the scripts by hand):
  - HISTOR host `histor-subregistry-switch.service`, started 04:03:46Z → `after.sh`: every 5 minutes, until 16:00Z,
    looks for the earlier rollout's `SWITCH-OK` and its last check line and for no open crawl run; then checks that
    the running image is `signed-fingerprints-20261119` and healthy, runs `switch.sh` (the image line and
    `HISTOR_SUBREGISTRY: "1"` in `docker-compose.warden-image.yml`), rolls back on failure, and logs health, the
    routes, and 15 minutes later the copy's state, tracebacks, memory and disk. If the earlier rollout was skipped or
    failed, this one is skipped too. Log `/root/histor-subregistry-20261120/after.log`.
  - admin-vps `histor-subregistry-rebind.service`, started 04:03:57Z → `rebind-after.sh`: rebinds MOMUS only when
    runtime.json reports e6ed85ce (10-minute polls, until 17:00Z). Log `/root/histor-subregistry-20261120/rebind.log`.
    (`<histor-host>` and `@NEW_IMAGE_ID@` in the copy here are filled in on the host.)
- Rollback by hand: HISTOR host `bash /root/histor-subregistry-20261120/switch.sh rollback` (drops the table, its
  four meta keys and schema row 26, restores the override, starts signed-fingerprints-20261119), then admin-vps
  `skopos-warden-quality rebind sha256:d81ba087c9b3f99749458be8bf1f2c8e12b9dce62f3fc364c5ef5afb8eebd524`.
- What appears when. The routes answer right after the switch, empty; 15 s later the first copy of the registry
  starts (about 680 pages; 4 min 22 s on a Mac against the official registry on 2026-11-19), then one read an hour.
- Known at scheduling: the alerter has "The disk of histor-vps is filling up" open (88 % used, 15 GB free at
  03:51Z); the copy was 92 MB as a whole SQLite store. `after.sh` logs the disk before and after.

Result: to be added after the run (read both logs; from outside:
`https://histor.modelmarket.dev/v0.1/servers?limit=1`, `/api/v1/subregistry`,
`/v0.1/servers/io.github.alexar76%2Fhistor/versions/latest` with its `dev.modelmarket.histor/observed` block).

## Result

Not switched. `after.log`: `2026-11-20T05:58:48Z SKIP: running image is histor-histor:warden-0.32.0-prod`. Production
moved to WARDEN 0.32.0 and then 0.33.0 images the same morning (other sessions), and the signed-fingerprints switch
this one waited for was held. The image `subregistry-20261120` is built on `signed-fingerprints-20261119` and is not
used. Deploying the subregistry needs a new overlay over whatever image is live then.
