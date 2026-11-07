# HISTOR on MTL/1.2: rollout 2026-11-06

What changed (aicom c85130d33; PROFILE.md "Revision 1.2"):

- **Labels.** Every label carries `profileRevision: "1.2.0"`.
  - A read set without a digest carries `toolSet.noDigest = {"reason": "not_digestible", "code": …}`.
  - A continuity label names each side without a digest under `noDigest.current` / `noDigest.prior`, with reason
    `not_observed` or `not_digestible`.
  - The prior side carries the revision its own label named, and is never guessed.
- **API.** `GET /api/v1/servers` returns `noDigest` (reason, or null when a digest exists).
  - `GET /api/v1/servers/{id}` adds `code`, `profileRevision` and `decidedAt` from the label that declined the set.
  - `profileRevision` is null for labels issued before this rollout.
- **Crawler.**
  - A package whose set an older revision declined, with an unchanged version, is run once more under 1.2.
  - An `undigestible` package judged by 1.2 is settled.
  - `package_signals.mtl` records the revision; it is excluded from security events.

Why: agent-control-standard#38 (avp9-nexus, 2026-11-06) asked a record to keep "nothing read" apart from "read and
declined by the profile". Our own 1.0 → 1.1 change had shown that "declined" holds only for a given revision, while
the descriptor's `mtl` stayed "1".

## Live

- Host: admin-vps, container `histor-histor-1`, compose `/opt/histor/docker-compose.postgres.yml`.
- Live since **2026-11-06 20:47:20Z** on `aicom-security:histor-histor-1-mtl12-20261106`
  = `sha256:ccdc15eba8814973abba02291eb4556596ae3bc6a306b6010a0c8d6cfe7c73a2`.
  - MOMUS binding re-bound to it.
  - Tagged `histor:warden-remediation-base`.
- Built FROM the running `aicom-security:histor-histor-1-seo-5aa4bce94` (`sha256:81e8e657…b9a1a0`).
- Overlay: `/app/histor/{app,labels,crawler,store,security_events}.py`. The live hashes of all five were checked
  before the build.
  - `labels.py`, `crawler.py`, `store.py` and `security_events.py` were byte-equal to the commit's parent.
  - `app.py` was not: it carries the seo change 5aa4bce94 (on side branches, not on main).
  - The deployed `app.py` is a three-way merge (`git merge-file`, no conflict) of this change onto the live file.
    Both versions are in `stage/` (`app.live-seo-5aa4bce94.py`, `app.deployed.py`).
  - **Before the next deploy from main**: main's `app.py` lacks the seo change, so a main build would drop it.
- MOMUS release gate passed (`20261106T032905`).
- Candidate smoke `stage/mtl12_smoke.py` ran on a disposable SQLite DB with `--network none`. It checked:
  - the overlay import path;
  - the revision constant in labels and the crawler;
  - an observation with `noDigest` NUM-001, verified with the AWR verifier;
  - a failed observation reported as `not_observed`;
  - `package_states`;
  - the list and server API (`not_digestible`, `not_observed`, code, `profileRevision`, `decidedAt`);
  - `/health` and `/log/checkpoint`.
- The first attempt failed in the smoke before the switch, so production was untouched (`rollout-attempt1.log`).
  `/log/checkpoint` has no signed head on an empty DB; the smoke now publishes one first.
- Backup: `/root/histor-backups/mtl12-20261106.fKOHFN5z` (compose file + the five previous host files).
  - The host's `histor/labels.py` already differed from the image's before this rollout; the backup holds the
    host copy.
- Kit on the host: `/root/histor-mtl12-20261106/`.

## Verified live (from outside, through nginx, ~20:50Z)

- `/api/v1/servers?state=undigested`: 812 servers (841 at 17:39Z; the restored package sandbox had already re-run
  some). Each has `noDigest: {"reason": "not_digestible"}`.
- `/api/v1/servers?state=unobserved`: 44,241 servers, each `{"reason": "not_observed"}`.
- A server page reads `{"reason": "not_digestible", "code": "MTL-NUM-001", "profileRevision": null,
  "decidedAt": "2026-10-20T21:55:11Z"}`. That set was refused under 1.0 by a pre-1.2 label, which is the case this
  change exists for.
- `/health` ok, crawl resumed.

## Seen during the rollout, not caused by it

The container's python is OOM-killed at its 1 GiB limit during crawls: 17:19:07Z and 19:28:58Z on 11-06, and 5
restarts since 11-05 04:00Z. That is the "interrupted: the process restarted before the crawl finished" in
`/health`.

## Rollback

On admin-vps as root:

```
cd /opt/histor
B=/root/histor-backups/mtl12-20261106.fKOHFN5z
cp -p "$B/docker-compose.postgres.yml" docker-compose.postgres.yml
for f in app labels crawler store security_events; do cp -p "$B/histor/$f.py" "histor/$f.py"; done
docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-deps --no-build histor
/usr/local/sbin/skopos-warden-quality rebind sha256:81e8e657a5088359c73785588cd9922542018f3deed7457ce369fc6787b9a1a0
docker image tag aicom-security:histor-histor-1-seo-5aa4bce94 histor:warden-remediation-base
```

Labels issued under 1.2 stay in the log after a rollback. That is harmless: 1.1 readers ignore the two members.
