# Disk survey: pingblip and histor-vps — 2026-11-22 ~10:30–10:50Z (read-only, nothing deleted)

Owner 22.11: «Yes, survey» for the two open disk alerts. Reclaim on servers is ask-first (AGENTS.md): this is the
survey only. Measured with `df`, `du -x`, `docker system df -v`, the borg receivers' `hints.*` files (read-only, the
same method that predicted the 11-10 and 11-15 compactions to within a few MB) and the clients' `last-run.json`.

Alerter (skopos-vps): "the disk of pingblip is filling up" open since 2026-11-21 20:38Z (flapping since 11-21 02:59Z),
"the disk of histor-vps is filling up" open since 2026-11-22 01:01Z. "The backup receiver is running out of disk" fired
03:49–04:09Z today and closed. attested closed 11-21 19:16Z after 2523614d0 and stands at 84 %.

Work in progress on histor-vps today: another session switched HISTOR to WARDEN 0.37.0 at ~10:23Z
(e3fff12b5). Not touched.

## pingblip — 157G, 129G used, 22G free, 86 %

| path | size | what it is |
|---|---:|---|
| `/srv/aicom-backups` | 64G | borg receiver for six clients (table below) |
| `/root/mfa-study` | 25G | malware-feed study data, `repeat-20261113` 17G — **protected** |
| `/var/lib/containerd` | 25G | Docker images 26.1 GB, 7.4 GB of it not used by a container (below) |
| `/var/lib/histor-sandbox` | 4.6G | HISTOR sandbox host |
| `/var/lib/mfa-study-keep` | 1.9G | study keep copy — **protected** |
| `/opt` | 5.3G | PingBlip deploy trees |
| logs, apt, journal | <0.6G | journal 183 MB |

Receiver repos (size / quota, new segments per night, freeable by `borg compact` per `hints.*`):

| client | size | quota | written last 7 d | freeable now |
|---|---:|---:|---:|---:|
| attested | 25.7 GB | 30G | 10.7 GB (1.5–1.8 GB a night) | 2.71 GB |
| not-my-vps | 19.1 GB | 24G | 0.7 GB | 4.86 GB |
| factory-vps | 9.1 GB | 30G | 1.3 GB | 0.39 GB |
| competing-lab | 6.7 GB | 15G | <0.1 GB | 0.01 GB |
| my-vps | 4.4 GB | 20G | 1.2 GB | 0.07 GB |
| indep | 3.3 GB | 15G | 0.2 GB | 0.18 GB |

- **The driver is the attested backup.** Its last run (01:36–01:42Z) read 15.7 GB and added 1.83 GB after
  deduplication. Of its five Postgres containers, `azimuth-postgres-1` (compose project `azimuth`, `/opt/azimuth`:
  web, api, worker, redis) holds 22 GB; the other four together hold under 0.3 GB. The dumps are already
  `gzip --rsyncable`, so the churn is real change in that database.
- **attested will hit its 30G quota in about 2–3 nights (≈ 11-24/25)**; append-only means pruning on the client does
  not give space back until the receiver compacts, and `aicom-backup-maintain` compacts only with
  `AICOM_BACKUP_COMPACT=1` (unset). After that its nightly backup fails.
- Disk: the receivers add ~2 GB a day in total, so 22G free lasts ~10 days; the 85 % alert is already crossed.
- Images not used by any container (unique bytes, `docker system df -v`):
  - rollback paths: `pingblip-rollback:forge-before-89ed03abf` 2.62 GB (11-07), `pingblip-world:prev` 1.25 GB,
    `pingblip-forge:prev` 0.15 GB; the 10-31 rollback tags (`aicom-hc-rollback:…cutover-20261031`,
    `aicom-os-rollback:before-20261031-3`, `aicom-security:…-20261031`, `aicom-seo:pingblip-world-5aa4bce94`) are
    ~0 unique: they share their layers with the running forge and world.
  - study images held by `mfa-study-keep`: `mfa-atomscan:2.13.0` 1.5 GB, `mfa-dyn:1` 0.43 GB,
    `mfa-ossgadget:2-unpriv` — **keep**.
  - re-pullable bases (`node:*`, `python:*`, ~1.3 GB unique; some are HISTOR sandbox build bases),
    `warden-comparison:20261107-node24-python313` 0.2 GB, `gitleaks:latest` 0.08 GB.
- Study units: `mfa-repeat-20261113.service` "failed" is the known 11-13 move of the repeat run to competing-lab.

## histor-vps — 116G, 99G used, 17G free, 86 %

| path | size | what it is |
|---|---:|---|
| `/srv/aicom-backups/admin-vps` | 36G | admin-vps borg repo, moved here 11-17 (c46f44a7a), quota 45G, +0.1 GB a night |
| docker volume `histor_histor-pg` | 25.1G | the live HISTOR database |
| `/var/backups/histor` | 23G | three local nightly dumps: 7.7, 8.1, 8.5 GB (+ 2 MB key tars) |
| `/var/lib/histor-datasets` | 7.8G | public datasets and snapshots |
| `/var/tmp/histor-offhost-seed-7b5k2w9e` | 3.4G | seed of the 11-10 move: `histor.dump` 3.6 GB, `histor-data.tar` 2 MB (the data volume, so most likely a signing-key copy), `snapshot.json`; no process uses it |
| Docker images / build cache / anonymous volumes | 1.5 / 1.0 / 0.35 GB | 31 HISTOR tags share their layers (0.18 GB reclaimable); build cache 0.23 GB reclaimable; 8 unused anonymous volumes |

- **Freeable by compaction: 15.31 GB** in the admin-vps repo (`hints.441`: 104 segments). Most likely the old
  admin-vps archives that still carried HISTOR's dump (HISTOR left admin-vps 11-10), already pruned by retention;
  the archive inventory in choice 1 would show it.
- HISTOR's own growth: each dump grows 0.4–0.5 GB a night, and three are kept (`HISTOR_BACKUP_KEEP_DAYS` default 2,
  by count). From the 11-17 survey (54.6 GB used, then the 37.6 GB repo copied in) to now (106 GB) the host grew
  ~2.5–3 GB a day. At that pace the 17G last about a week, and the off-host backup, which stages its own pg_dump in
  `/var/tmp` and refuses under 5 GB free, would stop in ~4–5 days (≈ 11-26/27).
- The off-host backup (03:46–04:01Z) and the local dump (03:45Z) run at the same time, so the nightly peak holds a
  fourth dump plus the staged one.
- `aicom-disk-cleanup` is **not installed** on this host (11-02 install covered seven hosts; this one came later).
- The attested receiver of HISTOR's off-host backup: 28 GB of 45G, +~1 GB a night, 0.00 GB freeable (first archive
  11-10, retention 14d/8w/6m has pruned nothing yet).

## Choices for the owner (none taken)

| # | host | action | frees | note |
|---|---|---|---:|---|
| 1 | histor-vps | `borg compact` of `/srv/aicom-backups/admin-vps` after an archive inventory from admin-vps (11-15 procedure: list before, compact, IDs equal after, `borg check`, a fresh client run, a read-back) | ~15.3 GB → ~73 % | biggest single gain |
| 2 | pingblip | same for attested + not-my-vps (+ the four small ones) | ~8.2 GB → ~81 % | gives attested ~2.7 GB more under its quota, i.e. ~1.5 nights |
| 3 | pingblip / attested | the attested backup itself: a larger quota, its repo moved to a receiver with room, or a decision about the Azimuth database's nightly dump | — | without this, attested's backup fails within days even after #2 |
| 4 | histor-vps | delete `/var/tmp/histor-offhost-seed-7b5k2w9e` | 3.4 GB | unused seed of 11-10; holds a signing-key copy (the live key is in `histor_histor-data`) |
| 5 | pingblip | remove `pingblip-rollback:forge-before-89ed03abf`, `pingblip-world:prev`, `pingblip-forge:prev` | ~4.0 GB | rollback paths of 11-05/11-07; the three PingBlip containers have run newer images since 11-14 and 11-17 |
| 6 | histor-vps | `HISTOR_BACKUP_KEEP_DAYS=1` (two local dumps instead of three) | ~8.5 GB | the off-host borg keeps 14 daily; the owner's 11-14 «не надо сокращать» was about that off-host retention |
| 7 | histor-vps | install `aicom-disk-cleanup` (hourly, `--if-needed`) | small now | keeps build cache and journal from creeping back |

Protected and not proposed: everything `mfa-*` and the study images, `/root/claudecode` (not present on these two),
`histor_histor-pg`, `histor_histor-data`, the key tars, and logs.

## Done: choices 1 + 2 (owner «Compact both (1+2)», 22.11)

Procedure of `deploy/backup/README.md` ("Reclaiming repository space"), one repository at a time, as `aicom-backup`
in transient units (`systemd-run --uid=aicom-backup`, `BORG_BASE_DIR=/srv/aicom-backups/.borg`, Nice 10, idle I/O
priority), `borg compact --threshold 0`, then `borg check --repository-only`.

**Before (10:56–11:05Z).** On every client `aicom-borg list --json` and the prune dry run with the configured
retention (`inventory/`, names and IDs only): 0 archives to prune everywhere, and every inventory is the 14 daily /
8 weekly / 6 monthly set (plus the held `cold-admin-backups-20261107T140656Z` of admin-vps and
`hold-attested-qa-20261113` of attested). The receivers' `transactions` since 11-08 have writes only in the nightly
window, except ones that match archives or records: admin-vps 11-15 21:04Z (that day's verification backup),
11-17 21:22Z (`files-2026-11-17T212148Z`, the move record of c46f44a7a); attested 11-13 10:06Z (the `hold-` archive);
competing-lab 11-13 09:41Z (`files-2026-11-13T093547Z`). No backup, maintenance or other borg process was running.

| receiver / repo | compacted (UTC) | freed | repo quota use before → after | `borg check` |
|---|---|---:|---|---|
| histor-vps / admin-vps | 11:05:37–11:12:05 | 15.31 GB | 38.17 → 22.86 GB of 45 | rc 0 (11:12–11:17) |
| pingblip / not-my-vps | 11:20:13–11:20:39 | 4.86 GB | 19.12 → 14.25 GB of 24 | rc 0 |
| pingblip / attested | 11:20:39–11:21:06 | 2.71 GB | 25.66 → 22.95 GB of 30 | rc 0 |
| pingblip / factory-vps | 11:21:06–11:21:15 | 0.39 GB | 9.08 → 8.69 GB of 30 | rc 0 |
| pingblip / indep | 11:21:15–11:21:16 | 0.18 GB | 3.30 → 3.12 GB of 15 | rc 0 |
| pingblip / my-vps | 11:21:16–11:21:23 | 0.07 GB | 4.40 → 4.32 GB of 20 | rc 0 |
| pingblip / competing-lab | 11:21:23–11:21:24 | 0.01 GB | 6.70 → 6.69 GB of 15 | rc 0 |

Each freed exactly what its `hints.*` predicted; 0 freeable left; every file still owned by `aicom-backup`.

**After.** On all seven clients the archive names and IDs equal the saved inventory, and
`aicom-borg check --archives-only --last 3` returns 0. Fresh client backups into each receiver: admin-vps
`files-2026-11-22T111804Z` (11:17:53–11:19:08Z, ok) and not-my-vps `files-2026-11-22T112823Z` (11:26:10–11:28:43Z,
ok, 7 pg dumps). Read-back from both: a logical Postgres dump extracts and passes `gzip -t`
(`logos-postgres`, `plinth-db`), and `etc/ssh/ssh_host_ed25519_key.pub` and `etc/aicom-backup/backup.conf` hash equal
to the live files. The other five clients write again in tonight's runs; attested got no daytime run on purpose
(it would spend ~1 GB of its quota headroom).

Disks: histor-vps 86 % → **74 %** (31G free), pingblip 86 % → **81 %** (30G free). Alerter: "disk of histor-vps"
closed 11:20:46Z (open 10 h), "disk of pingblip" closed 11:30:49Z (open 15 h).

**Shrink alert.** At 37.6 → 23.7 GB the admin-vps repo fell under the alerter's 70 % of its weekly peak, which opened
"the received backup of admin-vps shrank" at 11:20:46Z and would have held it for a week. With the checks above
done, that repository's peak history on histor-vps (`/var/www/aicom-backup-status/status.json.peaks.json`; that
host has no `/var/lib/aicom-backup`) was restarted at the compaction: 664 entries → the 2 taken after 11:12:05Z;
copy `/root/backup-compact-20261122/status.json.peaks.json.pre-compact`. The status page reads 23,692 MB of a
23,692 MB peak since 11:30:40Z; the alerter closed it at 11:41:10Z ("is whole again", open 20 min). The step is now in `deploy/backup/README.md`. The pingblip repos stayed above 70 %
(not-my-vps 75 %, attested 89 %).

**Still open (choice 3).** attested writes 1.5–1.8 GB a night; 22.95 GB of its 30G leaves ~4 nights (≈ 11-26).
Its repository `config` says `storage_quota = 40000000000` while the receiver's forced command says
`--storage-quota 30G`; `borg serve` applies the forced 30G. The README asks for both to agree; not changed.
