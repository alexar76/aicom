# HISTOR: record `instructions` on prod (scheduled 2026-11-16 after the crawl)

Owner 2026-11-15: «пусть краулер записывает instructions при обычных запусках», then "After the crawl, ~06Z".

- Image `histor-histor:instructions-20261115` = sha256:6f77067dbab32aac794e6f80fb7e05dad1ee5e1d7290ea852d188bf0ae2afc0d,
  FROM the live `landing-scanner-20261115` (f2660c5f) + main f8ed320e8 (see `Dockerfile`). Loaded on admin-vps too.
- Migration 024 (`ALTER TABLE observations ADD COLUMN instructions TEXT`) rehearsed 2026-11-15 on a throw-away
  Postgres 16: new image 0→24; old image refuses 24 ("database is at revisions [24] this build does not know");
  after the rollback SQL the old image accepts 23; new image re-applies 24.
- Scheduled, both transient one-shot timers (lost on reboot; then run the scripts by hand):
  - HISTOR host `histor-instructions-switch.timer` 2026-11-16 05:30:00 UTC → `after-crawl.sh`: waits (5-min polls,
    until 10:00Z) for no open crawl run, checks the running image, runs `switch.sh`, rolls back on failure, after
    15 min logs how many new observations carry `instructions`. Log `/root/histor-instructions-20261115/after-crawl.log`.
  - admin-vps `histor-instructions-rebind.timer` 05:45:00 UTC → `rebind-after.sh`: rebinds MOMUS only when
    runtime.json reports 6f77067d (10-min polls, until 11:00Z). Log `/root/histor-instructions-20261115/rebind.log`.
- Rollback by hand: HISTOR host `bash /root/histor-instructions-20261115/switch.sh rollback`, then admin-vps
  `skopos-warden-quality rebind sha256:f2660c5fcbb4c3fbdaa5fc0058f66a8c8910d17ae29b5473854bc5b1c19a5d51`.
- Packages: the sandbox observer that reports `instructions` is in main but not on the sandbox hosts (next observer
  rollout + MOMUS re-pin). Until then package observations store NULL (not read).

Result: to be added after the run.
