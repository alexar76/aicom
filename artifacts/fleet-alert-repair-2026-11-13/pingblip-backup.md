# PingBlip nightly backup recovery, 13 November 2026

PingBlip runs `aicom-backup.service` from the enabled `aicom-backup.timer`. It encrypts Borg archives locally, then sends them to the dedicated repository on the attested host. The monitoring host reads PingBlip's outgoing result from the IP-restricted status page. All times below are UTC.

| Time | Evidence |
|---|---|
| Nov 12 02:14:26 | Last successful run before incident finished. Archive `files-2026-11-12T021215Z`, one PostgreSQL dump. |
| Nov 13 01:41:10 | The nightly service started. Docker logged a container whose init process was no longer running 15 seconds later. |
| 07:41:10 | Systemd terminated the job with `Result=timeout`, SIGTERM 15, after six hours. The receiver still had its Nov 12 transactions. |
| 09:33 | Verified the installed script hash was `e83330d6d3d643b42ed7115c10caff700f05631d7a30f66039363b4d617ee256`. The status page was fresh and showed the old archive only. |
| 09:34:22 | Atomically replaced `/usr/local/sbin/aicom-backup` with the checked-in fix, preserving the previous file at `/var/lib/aicom-backup/aicom-backup.before-20261113T093421Z`, and started the existing service. |
| 09:35 | The retry passed the Docker discovery loop and staged a 4,729,681-byte `pingblip-postgres-1.sql.gz`. |
| 09:53–09:56 | Briefly set I/O class to low best-effort for the running SQLite discovery PID only. Measured no speed-up and restored the original idle class. Public PingBlip and World pages returned HTTP 200. |
| 10:10 | The retry was still advancing through research files. The snapshot process reported 1.467 GB of disk reads and the monitor still reported stale. |
| 10:12–10:13 | SQLite discovery left the repeat-run snapshot and passed through the Stage 3 input tree and `/opt`. |
| 10:14:46 | `borg create` took over and connected to the remote encrypted repository. |
| 10:46:15 | Received transaction `274` while the source still ran. The first transaction was consistent with Borg's periodic checkpoint. |
| 11:10:26 | Attested recorded transaction `279` after the archive creation phase. |
| 11:11:07 | Source service exited successfully after transaction `283` at 11:11:06. Archive `files-2026-11-13T101447Z` reported 10,883 MB original data, 964 MB deduplicated data and one logical PostgreSQL dump. The timer remains enabled. |
| 11:12 | Borg opened the archive metadata and listed `var/tmp/aicom-backup/pg/pingblip-postgres-1.sql.gz` at 4,729,681 bytes, matching the staged dump. The status page still held its 11:07 publication. |
| 11:17:31 | The normal status timer published the successful run. At 11:17:53 both `backup_status_published` and `backup_fresh[pingblip]` passed from the monitoring host. The persisted alert state showed `alerted: false` and `failures: 0`. |

The installed fix is [`deploy/backup/aicom-backup.sh`](../../deploy/backup/aicom-backup.sh) at `a8134bd678c1c47aa491b3c00c390623fcaec0d4`. Its SHA-256 `b84950e8258df088963f815dd290bba76f6dae7311792cedc365c3086a8baa17` was verified on both ends and the staged script passed `bash -n`. The patch bounds Docker discovery, readiness checks, volume lookup and database dumps. Timer settings, backup scope and retention were kept. At diagnosis the source had 35 GiB free and the receiver 18 GiB free. The PingBlip repository used 3.0 GiB against a 10 GB quota.

## File discovery during the retry

The SQLite scanner walks the backup roots even when it finds no SQLite databases. It advanced through the active 13 November study under `/root/mfa-study/repeat-20261113/snap`, spending time on metadata for the sparse public Git checkouts. The four indexed working copies report 860,165 tracked index entries in total. Index counts describe the checkout metadata and can include sparse entries. Live sampling found active research workers under gVisor and an independent incoming Borg process. That incoming process serves a different repository and does not report progress for PingBlip's outgoing backup.

| Raw checkout | Recorded commit | Indexed entries |
|---|---|---:|
| `ossf-old` | `ef188da1c8d1af253a585af8362997df142e1f36` | 239,971 |
| `ossf` | `02c60e05967e0208f13e3174eea210d7e902b7f9` | 240,926 |
| `vulnetix-old` | `a21bd56f5a257df6016129a3e164553722267da6` | 179,557 |
| `vulnetix` | `5f0afbd5a343a1dbc5571574e2d4e3c610be14e8` | 199,711 |
| `dd` | `72c723be547033c558244520524b117c8d71663b` | Blobless catalogue with selected fetches |

The refs come from the checkouts and the [study repeat procedure](../../research/malware-feed-accuracy/repeat/run_repeat.sh). This classification concerns only the raw checkouts. The GHSA directories hold point-in-time API responses. The date-specific selections, scanner results, local package sets, logs and annotations are study inputs or outputs. The running backup retains the full configured scope.

The successful run skipped one transient HISTOR sandbox after its Docker probe reached the new 30-second limit. Borg also reported two files changing during the archive scan. `last-run.json` records no errors.

Archive ID `b3b35d60e3ab8444c77ebd3c962518e67e2c95590b2e6cf6500c1b449b0b75f6` carries 797,867 items. Borg reported 10,882,947,943 original bytes and 964,066,117 deduplicated bytes.

## Verification

1. On PingBlip, read `/var/lib/aicom-backup/last-run.json` and confirm the retry is successful, `finished_at` is on 13 November and it lists a PostgreSQL dump. Take `archive` from that result.
2. On attested, verify `/srv/aicom-backups/pingblip/transactions` has a commit for the retry. On PingBlip, use the existing `aicom-borg` client to confirm the name and archive ID with `aicom-borg info --json ::ARCHIVE`.
3. Verify the dump entry's pathname and byte size with `aicom-borg list --json-lines` scoped to that entry. The backup job's successful `pg_dumps` count includes an on-source `gzip -t` before archival. Full encrypted dump read-back remains pending. Automatic approval denied the combined read-back and manual status-refresh call because it would decrypt a potentially sensitive production PostgreSQL dump and mutate the status page. An authorized restore operator can read and validate the dump under the [backup runbook](../../deploy/backup/README.md#restore).
4. Let the regular status timer publish the successful run. Query the deployed monitor's `probe_backups` from the monitoring host and verify `backup_status_published` and `backup_fresh[pingblip]`.
