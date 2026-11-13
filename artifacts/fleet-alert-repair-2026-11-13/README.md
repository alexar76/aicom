# Fleet alert repair, 2026-11-13 UTC

## WARDEN ERC-8004

After HISTOR's public endpoint moved, the new edge looked for feedback reports on its own filesystem. The weekly publisher and its files were still on admin-vps. The edge now proxies GET and HEAD for the feedback prefix to the publisher over TLS with certificate verification.

The [public summary](https://histor.modelmarket.dev/.well-known/erc-8004/feedback/last-run.json) returned HTTP 200. Its SHA-256 and that of `warden-1135050-20261109.json` matched the publisher's files. The summary shows the successful November 9 run at 09:10:09 UTC. The next weekly publish was scheduled for November 16 at 09:06:52 UTC. The tracked nginx template was also tested on nginx 1.27 and 1.30 with both local files and a configured proxy.

At 10:19:50 UTC the scheduled notifier completed successfully and reset the 404 counter from 51 to 0.

## Nightly backups

On competing-lab and PingBlip, a Docker exec probe into an ephemeral sandbox stalled until the six-hour service limit. Both source hosts received the bounded Docker probe and database command handling from `deploy/backup/aicom-backup.sh`. The nightly timers kept their schedules.

- **competing-lab.** Archive `files-2026-11-13T093547Z` committed on its receiver at 09:42:09 UTC. The run reported two PostgreSQL dumps and 70 SQLite snapshots. Both PostgreSQL dumps were extracted from the encrypted repository and passed `gzip -t`. The report records one timed-out probe of a HISTOR sandbox.
- **PingBlip.** Archive `files-2026-11-13T101447Z` committed on attested at 11:10:26 UTC. The service finished successfully at 11:11:07 UTC. Its status published on schedule at 11:17:31 UTC and ARGUS confirmed freshness. The archive has 797,867 items, including the 4,729,681-byte PostgreSQL dump. The job validated its gzip stream before upload, and the expected path and size were checked in the remote archive index. Automatic approval review rejected the combined operation to decrypt the potentially sensitive SQL and refresh the status manually, so full SQL read-back wasn't performed. Two research files changed while Borg read them, and one transient scanner was skipped after a Docker probe timeout. See the [retry timeline and verification](pingblip-backup.md).

## Root filesystem pressure

- **competing-lab.** Removed 29 abandoned HISTOR working directories (2,606 MiB) and 2,563 MiB of generated build and analysis caches. The cleanup service had separately stalled on a Docker container inventory. Bounding the Docker calls let the service finish on a real inventory timeout, while skipping tagged image deletion because the inventory was incomplete. A synthetic failure reproduced that behavior. Local `df` fell from 89% at first inspection to 83% at 09:51 UTC.
- **factory-vps.** Compressed and verified a retained recovery archive, then removed inactive build and package caches and old QA Python environments. Local `df` moved from 89% to 84% at 09:54 UTC.
- **attested.** Compressed and verified the previous nginx access log, enabled its stock rotation timer and removed regenerable test dependencies and vulnerability scan cache. Archived two inactive QA trees, `/opt/warden-tests` and `/opt/aicom-verify`, with metadata and 127,991 file checksums. The separate encrypted Borg archive `hold-attested-qa-20261113` (ID `89de2361b2533979ae9f2e505858872c8d664e8c2510e41177af68dd4937e70f`) passed a complete off-host SHA-256 read-back at 10:11:45 UTC. After the source trees were compared with the archives once more and retired, local `df` reported 84% and 25G available at 10:16:19 UTC. The incoming PingBlip archive temporarily pushed usage back to 85%. The host keeps the manifests and instructions for restoring the two QA archives at `/var/lib/aicom/maintenance-archives/qa-20261113`. The nightly job only prunes `files-*`, so this manual recovery point stays outside its rotation.
- The ordinary cleanup service now has bounded Docker calls and a 30-minute systemd timeout on all three affected hosts. The first scheduled runs with the new code on factory-vps and attested completed successfully around 10:02 UTC.

The [filesystem evidence](factory-attested-disk.md) records the original sizes, cleanup eligibility and health checks. The existing ext4 reserve was preserved on all three hosts.

After the attested QA archive commit, the receiver's freshness field reflects that repository transaction. The attested source's last nightly backup is independently recorded as successful at 02:53:25 UTC, archive `files-2026-11-13T025027Z`. After the QA move, the attested public site, Hub and Metis Appeal returned HTTP 200 and all 40 running containers reported no unhealthy status.

After the PingBlip commit, retiring the remaining local compressed QA copy and clearing or compacting 333,479,936 bytes of reproducible package dependencies and indexes brought attested back to 84% at 11:19:26 UTC. Available space was 25,984,847,872 bytes. About 231 MB of additional writes at unchanged filesystem size would take its displayed usage back to the 85% alert threshold.

The 11:22 SKOPOS report uploaded its previous cached privileged disk probe. The new probe completed at 11:23:02 UTC and reported 84%. The separate reporting timer sends that value on its next run. The export timestamps disk rows at ingestion, so the ingestion timestamp can be several minutes newer than the underlying measurement.

The 10:19 UTC scheduled full check reported 160 of 161 passing and confirmed all three disk checks and competing-lab backup recovery. The only open check in that run was the PingBlip backup. Unlike incoming repository commit timestamps, PingBlip's monitor checks the outgoing job's own completion report, so an intermediate Borg checkpoint cannot clear that alert. The receiver wrote an intermediate transaction at 10:46 UTC while the source Borg process was still working.

The full read-only watcher run at 11:28:11 UTC reported **161 of 161 checks passing**, including every affected disk and both recovered backups.
