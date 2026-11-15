# HELIOS on attested, 2026-11-15: asset roots, upload-cap pause, one re-queue

## What was wrong

HELIOS published nothing after 2026-11-05. The YouTube token was valid (refresh OK, `channels.list` answered).
Two causes, one after the other:

1. **Render.** Prod `/root/helios/helios.config.yaml` listed only `/data/assets`. The visual catalogue names
   `platon-umbral-hero.gif` for oracles/platon topics, a file only in `/root/helios/assets` (mounted at
   `/app/assets`). Every render of the trust-and-proof season failed on 11-08, 11-11 and 11-14
   ("asset not found in roots"). Fixed: `/app/assets` added as a second root (backup
   `helios.config.yaml.bak-20261115-assets`); template fixed in main 13f6d32e8.
2. **Upload.** The re-run rendered in ~70 s, then YouTube refused it: `uploadLimitExceeded`. A 10-Short batch
   (PromoMaterials ecosystem-series, season66) had been uploaded to the same channel at 05:27Z. The old worker
   kept the job pending and rendered it again every ~3 minutes (12 times in 40 minutes).

## Upload-cap pause (this kit)

`pause.diff` = main 95b6f8bf4 (worker.py, queue.py). The prod image predates main, so the diff was applied to
the image's own two files and nothing else (`patch` output: only these hunks). `Dockerfile` builds
`aicom-security:helios-worker-pause-20261115` FROM `helios-worker-tts-20261105`.

- `smoke.py`, run in the new image on a throwaway data dir with no network: exit codes 2 2 2, one attempt,
  job still pending, pause set for 6 h; after the pause ends, exactly one more attempt. `SMOKE-OK`.
- Live 2026-11-15 ~09:30Z: `docker-compose.isolated.yml` names the new image for `helios-worker` only (backup
  `docker-compose.isolated.yml.bak-20261115-pause`); recreated with
  `docker compose -p helios -f docker-compose.yml -f docker-compose.isolated.yml up -d --no-deps --no-build helios-worker`.
  Inside: patched md5s, both asset roots, platon asset resolves, mounts and read-only root unchanged,
  `HELIOS_AUTO_APPROVE=0`, no errors. The API container `helios` is unchanged.
- Rollback: `cp docker-compose.isolated.yml.bak-20261115-pause docker-compose.isolated.yml` and the same
  `up -d --no-deps --no-build helios-worker`.

## Re-queue (owner's yes)

`requeue-20261116.py` runs once from the transient timer `helios-requeue-20261116` (2026-11-16 06:00Z). It
skips when the channel has >= 10 uploads in the last 24 h or the episode is already queued or done; otherwise
it enqueues the Platon UMBRAL episode again with the same script and idempotency key. A dry run on
2026-11-15 08:19Z printed `uploads in last 24 h: 10` and `SKIP`. The video uploads private and needs
`helios approve <job>`. Log: `/root/helios/requeue-20261116.log`. The timer does not survive a reboot.

## Description review (same day, `desc/`)

The 2026-11-08 video was blocked for "a description ending in a truncated URL (https://oracles.modelmarke)".
The description was whole: 505 characters, ending in `https://oracles.modelmarket.dev`. The metadata
reviewer (`director.review_metadata`) received only the first 500 characters. Fix (main dd33912dc): the
reviewer reads the whole description up to YouTube's 5000; anything longer is cut at a space and labelled as
shortened for the review. Calliope's own 4000-character cap now cuts at whitespace too.

`desc.diff` applied to the image's own `director.py` and `calliope.py`; image
`aicom-security:helios-worker-desc-20261115` FROM `helios-worker-pause-20261115` (the pause stays).
`desc/smoke.py`, run with the real 11-08 job's metadata (read-only copy), printed the reviewer's input ending
in `https://oracles.modelmarket.dev` and `SMOKE-OK`. Live ~10:00Z; compose backup
`docker-compose.isolated.yml.bak-20261115-desc` (rollback = that file + `up -d --no-deps --no-build helios-worker`).
The 11-08 video was not re-queued: the reviewer also objected to its title ("proves its own math").
