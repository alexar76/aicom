# HISTOR: observer-5 false failures run once more (crawlretry-20261116, 2026-11-16)

Owner, 11-16: the observer-5 false failures were fixed in the sandbox observer (artifacts/histor-observer-idfix-2026-11-16).
But crawler.SETTLED keeps `protocol` and `exited` until a new package version, and the observer number stayed 5. So 121
targets (119 protocol, 2 exited naming server/discover) would never have been read again. Coordinated with session
qa flow, which owns the instructions rollout and asked for this order: after its SWITCH-OK and REBIND-OK, built from its image.

## Change

- `histor/histor/crawler.py` = aicom main e07eb9641: `_early_observer5_failure`, cutoff `OBSERVER5_FIXED_AT =
  2026-11-16T04:37:00Z` (observer bf8fe5b8 on every sandbox host).
- A last attempt before the cutoff by observer 5 with status `protocol`, or `exited` naming server/discover or
  ExpectedInitialize, is not settled: it runs once more. Failing again under the fixed observer, it is settled.
- Tests: 4 cases in `histor/tests/test_packages.py` (3 fail without the change).
- Image `histor-histor:crawlretry-20261116`, sha256:fce417bc5ef6d1316e3549be7ff1a0243fe97299571f393cd23b225ed1b083f4.
  It is FROM `histor-histor:instructions-20261115` (6f77067d) plus this one file. The image's crawler.py equalled main
  e07eb9641^ (sha256 ab43d4d6…), so the file is main's whole. No migration; the database stays at 24.

Kit on the HISTOR host: `/root/histor-crawlretry-20261116/` (Dockerfile, ctx/, switch.sh, new-image-id, switch.log).

## Rollout (server clock, UTC)

1. qa flow's steps finished first:
   - crawl 396663 finished 06:21:45Z;
   - SWITCH-OK 06:25:42Z;
   - REBIND-OK 06:35:02Z;
   - its post-switch measurement was logged at 06:40:43Z (1,275 observations with instructions read, 0 remote polling
     failures), before this restart.
2. The image was copied to admin-vps by `docker save | gzip | docker load`, as MOMUS extracts WARDEN from the local image.
   The image ID was the same.
3. `switch.sh` at 06:41:28Z: health healthy, running image fce417bc. Runtime page
   `/.well-known/aicom-histor-runtime.json` shows fce417bc.
4. MOMUS: `skopos-warden-quality rebind sha256:fce417bc…` rc 0. The WARDEN build is unchanged (403842d7), so the binding
   moved without a new measurement. Backup: admin-vps `/root/histor-crawlretry-20261116/live-image.json.pre`.
5. After: remote polling runs continue (167 observations in the first minute), 0 error lines in the container log.
   `/health`, `/api/v1/check` and `/datasets/` answer 200.

The effect shows in the next package crawl (~2026-11-16T18:2xZ): the 121 targets are run again; stats show them under
`packages.incompleteRetries`.

## Rollback

`/root/histor-crawlretry-20261116/switch.sh rollback` puts back `instructions-20261115`; then on admin-vps
`skopos-warden-quality rebind sha256:6f77067dbab32aac794e6f80fb7e05dad1ee5e1d7290ea852d188bf0ae2afc0d`. Never further
back than instructions-20261115: older images refuse migration 24. Going below 24 is qa flow's
`/root/histor-instructions-20261115/switch.sh rollback`.
