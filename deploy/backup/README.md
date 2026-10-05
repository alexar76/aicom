# Off-host backups

Every server sends an encrypted nightly backup to another server. Until 2026-10-04 nothing
left any host: the hub keys, the credit ledger and the HESTIA tenants lived on one disk.

| what | where |
|---|---|
| receiver of everything | PingBlip, `82.21.72.167:/srv/aicom-backups/<label>` |
| receiver of PingBlip's own backup | attested, `162.141.123.165:/srv/aicom-backups/pingblip` |
| schedule | nightly between 01:30 and 03:30 UTC (`aicom-backup.timer`) |
| retention | 14 daily, 8 weekly, 6 monthly archives (`files-<UTC time>`) |
| passphrases | on each host in `/etc/aicom-backup/passphrase`, and on the owner's Mac in `~/.aicom-backup/<label>/` |
| freshness | `https://pingblip.com/.aicom/backup-status.json` (alerter's IP only) → alerter check `backup_fresh[<label>]` |

## What is in an archive

- `/etc /root /home /opt /srv /usr/local /var/www /var/spool/cron /var/lib/docker/volumes`
  plus per-host extras (`EXTRA_ROOTS` in `/etc/aicom-backup/backup.conf`), minus
  `/etc/aicom-backup/excludes`: package trees, caches, build output, docker-in-docker stores,
  metrics, stale copies.
- Every running Postgres: `pg_dumpall` → `var/tmp/aicom-backup/pg/<container>.sql`
  (`host-postgresql.sql` for a host Postgres). The raw data directories are left out.
- Every SQLite file, copied through SQLite's backup API →
  `var/tmp/aicom-backup/sqlite/<original absolute path>`. The live file is left out.

## Security model

- **Encrypted on the source** (`repokey-blake2`). The receiver stores ciphertext and never
  has a passphrase. Passphrase + exported key are on the source and on the owner's Mac.
  Keep an **offline copy of `~/.aicom-backup`**: without it the archives cannot be read.
- **Append-only.** A source's ssh key is pinned in the receiver's `authorized_keys` to
  `borg serve --append-only --restrict-to-repository /srv/aicom-backups/<label> --storage-quota N`.
  A source that is broken into can add archives, but cannot delete or rewrite old ones, read
  another host's repository, or fill the receiver past its quota.
- Space freed by prunes comes back only when the **receiver** runs `borg compact`
  (`aicom-backup-maintain.timer`, Sundays 12:00 UTC; also `borg check --repository-only`).

## Everyday commands (on the source host, as root)

```bash
systemctl start --no-block aicom-backup    # back up now
cat /var/lib/aicom-backup/last-run.json    # result of the last run
aicom-borg list                            # archives
aicom-borg info ::files-2026-10-05T021500Z # one archive's size
```

## Restore

On the source host (or any machine with borg, the passphrase and ssh access to the receiver):

```bash
mkdir -p /var/tmp/restore && cd /var/tmp/restore
aicom-borg list
aicom-borg extract ::files-2026-10-05T021500Z var/lib/docker/volumes/modelmarket_hub_data
aicom-borg extract ::files-2026-10-05T021500Z var/tmp/aicom-backup/sqlite/var/lib/docker/volumes/modelmarket_hub_data
aicom-borg extract ::files-2026-10-05T021500Z var/tmp/aicom-backup/pg/hestia-hestia-postgres-1.sql
```

- SQLite: copy the snapshot from `var/tmp/aicom-backup/sqlite/<path>` back to `<path>` (with the
  service stopped). Do not restore a `-wal`/`-shm` next to it: the snapshot already contains them.
- Postgres: `docker exec -i <container> psql -U <user> -d postgres < <container>.sql` into an
  empty server (the dump carries `--clean --if-exists` and the roles).

**From another machine** (the source host is gone). On the Mac or a fresh server with borg:

```bash
export BORG_REPO=ssh://root@82.21.72.167/srv/aicom-backups/factory-vps
export BORG_PASSCOMMAND="cat $HOME/.aicom-backup/factory-vps/passphrase"
borg list
borg extract ::files-2026-10-05T021500Z etc/nginx
```

Root on the receiver can open any repository path. If a repository's own key was ever lost
or damaged, import the exported one first: `borg key import $BORG_REPO ~/.aicom-backup/<label>/repokey`.

## Undo a malicious prune

Append-only mode keeps a transaction log (`/srv/aicom-backups/<label>/transactions`). If a
source was broken into and "deleted" archives, do it **before Sunday's compact**: stop the
timer, then follow borg's "append-only mode" notes — delete the newest `index.N`/`hints.N`/
`integrity.N` and the segments after the last good transaction, and run `borg check`.

```bash
systemctl stop aicom-backup-maintain.timer   # on the receiver, first
```

## Adding a host

```bash
deploy/backup/install.sh HOST LABEL root@82.21.72.167 82.21.72.167 15G [EXTRA_ROOT...]
ssh HOST systemctl start --no-block aicom-backup
```

Then add LABEL to `AICOM_ALERT_BACKUP_HOSTS` on the alerter host.
