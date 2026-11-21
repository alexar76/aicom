# attested: disk alert, three unused database folders removed — 2026-11-21

The disk alert on attested had been open for about two days. At 18:50Z `/` was at 87% (130 of 157 GB, 21 GB free).

**Survey (read only):**

| Size | Path | What |
|---|---|---|
| 27 GB | `/srv/aicom-backups` | backup copies: histor-vps, pingblip (kept) |
| 22 GB | `/var/lib/aicom/postgres/azimuth-hc-1793509330514590583` | live database of `azimuth-postgres-1` |
| 35 GB | `/var/lib/containerd`, plus 27 GB `/var/lib/docker` | images and volumes; no prune on this host |
| 7.4 GB | three folders below | not mounted by any container |

**Removed** (owner 21.11 «Yes, delete them», for exactly these three paths) at about 19:00Z:

- `/var/lib/aicom/postgis/azimuth-1793474900985209796` (3.7 GB, 31.10)
- `/var/lib/aicom/postgis/azimuth-1793475399927083344` (3.5 GB, 31.10)
- `/var/lib/aicom/postgres/multica-hc-1793508838472981987` (148 MB, 01.11)

**Checked before removing:**
- No container, running or stopped, mounts them.
- None of them has the immutable flag.
- No process has a file open in them.
- Nothing in them was written after 01.11.
- No unit file or script names them.
- No `mfa*` unit is on the host.
- The colleague-tasks file does not mention them.

The live folders `azimuth-hc-…3330514590583` and `multica-hc-…3226390777083` were not touched.

**After:** `/` at 82% (123 GB, 28 GB free). All azimuth and multica containers are up, and both databases are
healthy. No Docker prune was run.
