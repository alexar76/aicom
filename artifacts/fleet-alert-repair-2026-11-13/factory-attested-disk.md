# Root filesystem capacity on factory-vps and attested

Investigation and controlled cleanup on 2026-11-13 UTC. SKOPOS pages at a reported disk usage of 85%. Its reported percentage comes from `df`, which rounds up.

| Host | Initial used / available bytes | Initial use | After direct cleanup, used / available bytes | Use |
| --- | ---: | ---: | ---: | ---: |
| factory-vps | 106,680,430,592 / 13,716,996,096 | 89% | 100,885,336,064 / 19,512,090,624 | 84% |
| attested | 142,672,871,424 / 18,287,817,664 | 89% | 139,070,951,424 / 21,889,736,704 | 87% |

## factory-vps

- Reclaimed 1,534,377,984 allocated bytes by compressing the 1,761,320,960-byte manual recovery tar under `/root/oracle-gateway-rollout-20261028/factory-vps--modelmarket-hub-uni/` to a 226,873,443-byte gzip. The decoded byte count and SHA-256 match the original `backups.json`. The archive remains private with a local restore note. The scripted container rollback does not consume the tar.
- Reclaimed 2,637,705,216 allocated bytes from the generated `target/debug/{incremental,deps,build,.fingerprint}` directories in `aimarket-sdks/rust`, `contracts/solana`, `awr/rust` and `acex/contracts/solana`. Verified Cargo cache markers, retained lockfiles, Git ignore status, cache age, and absence of process references and mounted copies. Packaged and release artifacts remain in place.
- Reclaimed 1,630,781,440 allocated bytes by clearing nine old QA `preview-venv` directories and the download caches `.npm/_cacache` and `.pip/http-v2`. Verified the empty preview registry, mounts in the host and nested Docker daemons, and process references. The Python environments are bootstrapped on demand. Preview databases, source, and other sandbox files remain in place.
- The published deployment image retention runbook found zero eligible tags. Docker reported about 1.65 GB reclaimable across images, including tags whose current evidence or rollback purpose remains relevant. The largest writable layer was about 17 MB. One active UNI relayer had about 1.53 GB of Docker `json-file` output. The log driver has no configured rotation for that container. Its log remains under Docker control.

## attested

- Installed the Ubuntu Noble `logrotate` package (`3.21.0-2build1`) and enabled its active timer. Ran the existing nginx rotation rule and confirmed the master PID stayed the same. The old inode was closed. A 789,421,683-byte access log compresses to 49,089,065 bytes at `/var/log/nginx/access.log.2.gz`. The decoded SHA-256 was verified before discarding the uncompressed copy. Existing retention remains in effect.
- Reclaimed 1,109,549,056 allocated bytes from 19 test-only `node_modules` directories in seven completed WARDEN runs from November 7–8. The matching package and lock files, source and results remain in place. The directories were unmounted and unused by processes.
- Reclaimed 1,764,945,920 allocated bytes from the disposable vulnerability database in the already completed `/root/argus/mail-oauth-20261112/security/cache/db/` scan cache. Verified the absence of open handles and bind references, and preserved the three completed scan reports and database metadata.
- The largest remaining consumers include October 31 emergency rollback archives, filesystem storage used by live services and test evidence. The routine off-host backup excludes the old emergency archive directories. Moving an archive would require separate durable storage and successful full read-back before retiring the local copy.

## Capacity and health

Both hosts use an ext4 root on `/dev/mapper/hk-root`, backed by `/dev/sda2`. The guest sees one oVirt virtual disk per host, 120 GiB at factory-vps and 160 GiB at attested. Both PVs and volume groups have zero free extents. The existing root reserve was preserved. At the direct cleanup checkpoint, factory had 248,502,354 bytes of margin before `df` returned 85%. Attested still needed 3,863,973,397 bytes reclaimed to reach a reported 84%, or about 4.60 GB more usable filesystem capacity at unchanged usage. The existing virtual disks have no provisioned headroom for guest-side growth.

Factory’s modelmarket.dev and UNI Hub home pages, AI Factory health endpoint and UNI Alien Monitor health check returned HTTP 200. Attested’s attestedmemory.net, hub.attestedmemory.net and Metis Appeal health check returned HTTP 200. The checks saw 39 and 40 running containers respectively, with zero reporting unhealthy. Both cleanup and backup timers were active. The latest nightly Borg jobs reported success. Factory archive `files-2026-11-13T014158Z` completed at 01:44:04Z with 228 SQLite snapshots. Attested archive `files-2026-11-13T025027Z` completed at 02:53:25Z with five PostgreSQL dumps and 21 SQLite snapshots. These values come from the recorded job status.

## Scheduled cleanup hardening

Factory and attested now have the bounded Docker commands and `TimeoutStartSec=30min` already installed on competing-lab. The script and unit were verified before and after atomic file replacement. A daemon reload applied the change. The existing timers and host-specific keep files were preserved. Cleanup was left to the scheduled `aicom-disk-cleanup.timer`.

| File | Installed SHA-256 |
| --- | --- |
| `/usr/local/sbin/aicom-disk-cleanup` | `6662ef1420735542d897dc1f37c9ad97c7988001bdb3daf3f4212e7693adec64` |
| `/etc/systemd/system/aicom-disk-cleanup.service` | `56bec3eb51dd944edfac35327ea972a2b35ba4f8a3c893653cba00b6744039b4` |
| `/etc/systemd/system/aicom-disk-cleanup.timer` | `de7b206b78dad9d061e7bddd52a5e43a24f41c7af7951a4a23d2a3a13dd9c2c2` |

The prior script and service are retained at `/var/backups/aicom-cleanup-deploy.OYqwOu` on factory-vps and `/var/backups/aicom-cleanup-deploy.sr9Zq5` on attested. Factory’s first scheduled invocation exited successfully at 10:02:22Z. Its 84% utilization fell within the daily full-run interval. Attested’s first scheduled full invocation exited successfully in 15 seconds at 10:02:39Z. The visible root usage at 10:03:29Z was 88% including concurrent archive staging.

## Attested follow-up after the incoming nightly backup

The new PingBlip backup and subsequent local staging briefly put attested at 85%. After the separate verified archival cleanup, the following scoped actions released 333,479,936 more allocated bytes.

- Cleared only apt’s generated `pkgcache.bin` and `srcpkgcache.bin` files while holding the apt lists, apt archives, and both dpkg locks. Source lists, installed packages, and dpkg state were preserved.
- Removed one 88 MB `node_modules` directory from the synchronized upstream Hephaestus Studio tree. Verified the preserved package manifest and lockfile, the dated dependency tree, host process usage and Docker mounts before removing the installed dependencies.
- Retained the WARDEN editorial dependencies in a 47,898,311-byte `deps.tar.zst` beside the project. Verified full tar comparison against the original files and provided a restore command beside the archive. The source, inputs, figures and reports remain in place.

At 11:19:26Z the root filesystem reported 84% with 134,975,840,256 used and 25,984,847,872 available bytes. The three public health probes returned HTTP 200 and none of the 40 running containers reported unhealthy. The scheduled SKOPOS report succeeded at 11:22:24Z with 32 accepted and zero rejected records. The next disk check showed 84% with 134,977,253,376 used and 25,983,434,752 available bytes, leaving 229,724,651 bytes of margin before a reported 85%.
