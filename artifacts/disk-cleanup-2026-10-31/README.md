# Disk cleanup on the alexar76 servers — 2026-10-31

Owner: «почисти место … сначала покажи мне список», then «Чисти А и Б» (A = caches, journals, apt; B = old copies by
the keep-the-newest rule). C (the security maintenance rollback points of 2026-10-31) and D (databases, borg backups,
the malware-feed study data, HISTOR sandbox images, repository checkouts) were left alone. my-vps was not touched.

| host | before | after | what went |
|---|---|---|---|
| admin-vps | 96% (4.1 GB free) | 88% (13 GB) | HISTOR dumps of 10-25..10-28 (the 3 newest and all keys tars kept), /var/backups/histor-v13-20261010, /root/dioscuri-tree-pre-20261017.tgz, 38 WARDEN/HISTOR build leftovers in /var/tmp from 10-18..10-26 (warden-0222-build kept), praxis:momus-* x5 and warden:metadata-diagnostic-ce1dd74ed, apt cache |
| pingblip | 79% (32 GB) | 43% (87 GB) | build cache 49.85 GB, the rekt-before-20261027 image set, journal 3.4 GB → 0.5 GB, apt cache |
| competing-lab | 60% (37 GB) | 40% (55 GB) | 33 modelmarket-hub / signal-hunt-hub tags created before 2026-10-01 (prod-20260928-topup380 kept: in use), build cache 3.5 GB, journal 4.0 → 0.5 GB, apt |
| attested | 42% | 38% (95 GB) | build cache 7.0 GB, apt |
| skopos-vps | 82% (11 GB) | 76% (14 GB) | build cache 2.6 GB, journal → 0.3 GB, apt 0.9 GB |
| indep | 56% | 53% (27 GB) | journal → 0.4 GB, apt. Old releases NOT removed: many services (AEGIS, capability, KOVA, monitor, portal, dayslap, ARGUS, claim-audit, escrow-signer) run from /opt/independentai/releases and venvs, and the hub's own WorkingDirectory is releases/aimarket-hub-3.15.16 under the 3.16.0 venv; a release map is needed first |
| factory-vps | 79% (25 GB) | 67% (38 GB) | run by the owner by hand (`clean-factory-vps.sh`; the auto-mode classifier refused it to me): the 168 old *-prev containers in `factory-vps-containers-to-remove.txt` (containers 300 → 132), the ai-factory tags brief / visitor-private* / naming / latest / local, dangling images, journal 1.1 GB → 0.47 GB, apt |

Kept on purpose: skopos-vps certbot/certbot (runs on renewal), metis:local; HISTOR sandbox images histor-node/histor-python
on pingblip and competing-lab (0 containers between runs). HISTOR's backup job prunes after 5 days
(HISTOR_BACKUP_KEEP_DAYS, /usr/local/sbin/histor-backup), so admin-vps returns to 5-6 dumps (~+3 GB).
The first inventory's "images not used" list was wrong (it compared image refs, not container image ids); the
numbers above come from `docker system df -v` (images with 0 containers) and `df`.
