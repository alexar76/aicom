# PingBlip disk: old backups and rollbacks cleared (2026-11-10)

Owner: «ну почисти старые бэкапы и вообще, случайно не грохни нужное».

Before the cleanup the disk was at 85–86 % (133.4 GB used of 157 GB), at the alert threshold. The 2026-11-09
restore of the malware-feed study data added about 7.5 GB, and the fleet backups PingBlip receives grow every
night. After the cleanup: 118 GB used, 79 %.

## 1. Backup repositories compacted (about 5 GB)

PingBlip receives the borg backups of seven hosts in `/srv/aicom-backups`. The repositories are append-only:
- a client's prune only marks archives as deleted;
- the space comes back when `borg compact` runs on the receiver;
- the maintenance timer deliberately never compacts on its own, so a compromised client cannot delete
  everything for good.

Its rule is to compact by hand after checking that no repository just lost its archives. Checked on each
client with `aicom-borg list`:
- admin-vps, attested, factory-vps and competing-lab have 19 archives each, indep and not-my-vps 18;
- the oldest is from 2026-10-04 and the newest from 2026-11-09 or 11-10;
- policy: 14 daily, 8 weekly and 6 monthly.

Compacted as the `aicom-backup` user (`/var/tmp/backup-compact-20261110.sh`, log
`/srv/aicom-backups/.compact-20261110.log`):

| repo | before | after |
|---|---:|---:|
| admin-vps | 34G | 34G |
| attested | 11G | 8.0G |
| competing-lab | 2.8G | 2.8G |
| factory-vps | 7.7G | 6.6G |
| indep | 3.2G | 2.9G |
| my-vps | 2.7G | 2.7G |
| not-my-vps | 18G | 17G |

No archive was removed: compaction frees only what the clients' own retention had already dropped.

The admin-vps repository needs 35.8 GB for the archives it keeps, against a storage quota of 40G on the receiver. Its October archives
are cheap (unique 0.07–0.69 GB each; the out-of-policy `cold-admin-backups-20261107T140656Z` holds 2.75 GB
unique). The growth comes from current data, mostly the HISTOR dumps.

## 2. Old rollback images of pingblip and world removed (about 5.8 GB)

Kept:
- the running images `aicom-seo:pingblip-pingblip-5aa4bce94` and `aicom-seo:pingblip-world-5aa4bce94`;
- one rollback each, `pingblip-pingblip:prev` and `pingblip-world:prev`, built 2026-11-04;
- forge, untouched: running `aicom-security:pingblip-forge-1-hc-live-20261031` and its 10-31 rollbacks, which
  would have freed only about 150 MB;
- postgres.

Removed, all from the 2026-10-31 security rollout:
- the created-only rollback containers `pingblip-pingblip-1-security-prev-1793483223300074433` and
  `pingblip-world-1-security-prev-1793483047038099099`;
- the tags `pingblip-pingblip:latest`, `aicom-security:pingblip-pingblip-1-20261031`,
  `aicom-os-rollback:before-20261031-1`, `aicom-hc-rollback:pingblip-pingblip-1-cutover-20261031`,
  `pingblip-world:latest`, `aicom-os-rollback:before-20261031-2` and
  `aicom-hc-rollback:pingblip-world-1-cutover-20261031`, which took the images with them (`docker rmi` without
  `-f`).

`deploy_pingblip.sh` tags the running image `:prev` itself before a new build, so it does not need the old
`:latest`. The inspect output of everything removed is in `/root/security-rollbacks/removed-20261110/` on the
host. All four PingBlip containers kept running.
