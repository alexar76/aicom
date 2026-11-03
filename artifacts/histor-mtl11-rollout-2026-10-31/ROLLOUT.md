# HISTOR MTL/1.1 rollout — 2026-10-31

Owner: «Да, выкатывай» (after «Да, чини» and «давай исправим … чтобы все хешировал»). Code: aicom 8e0763168
(local main fast-forwarded to it; not pushed to Gitea at the time of writing). Times are admin-vps clock (UTC).

## What ran

Overlay on the running image, nothing else changed: `histor/{subject,labels,crawler,store}.py` and
`docs/landing/assets/desk.js` (`Dockerfile`, hashes in `expected.sha256`). The running image was the security
rollout's `aicom-security:histor-histor-1-python-20261031` (4f08c5c5c617); its `/app` equalled main except
`histor/app.py` and `histor/__init__.py` (main's fingerprints endpoint and 0.5.2, someone else's, not deployed),
which the overlay keeps. The service imports `/app/histor` (`python -m histor serve` from `/app`); the copy in
`/opt/venv/.../site-packages/histor` is shadowed. No migration (schema stays 17).

`deploy.sh`: tag running → `histor-histor:pre-mtl11-20261031`; build `histor-histor:mtl11-20261031`
(79627d045e1c); `smoke.py` inside it with no network (file hashes, the 8 shared vectors, NUM-001 only for 1e400,
SUBJ-001 for a nameless entry, the new label/crawler/store code present); MOMUS release gate passed
(20261031T033115, build 3b6b074c…); WARDEN dist identical in base and new; compose image line switched in
`/opt/histor/docker-compose.postgres.yml` (copy kept as `.pre-mtl11-20261031`); `compose up -d --no-build histor`;
health 16:42:17Z; MOMUS quality binding moved to 79627d045e1c and tagged `histor:warden-remediation-base` (it was
on fdb74875531b, the pre-security image). First attempt aborted in the smoke test before any swap
(`deploy-1-smoke-path.log`: the test imported the shadowed site-packages copy; fixed with PYTHONPATH=/app).

Compose also recreated `histor-histor-postgres-1` on the same image (0cefaabd882e, pinned in the file by the
security session without recreating the container); it was back healthy within seconds, data intact (1,326,154
labels, schema 17, 42,050 changes).

## Verified

- /health ok, tree grows; `/api/v1/stats` targets: listed 89,113, pinned 42,646, undigested 5,164 at deploy;
  `state=unobserved` 41,303 = listed − pinned − undigested.
- Public `POST /api/v1/check` with `"default": 0.7` returns a digest, no `digestError`.
- 16:50Z (8 min after): pinned 42,697, undigested 5,113; 52 continuity labels `inconclusive`, reason
  `MTL-NUM-001` "the prior tool set had no digest"; 8 changes recorded = 8 `fail` labels (real changes); the
  first-digest transitions recorded no change.

## Rollback

    cp /opt/histor/docker-compose.postgres.yml.pre-mtl11-20261031 /opt/histor/docker-compose.postgres.yml
    cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-build histor
    /usr/local/sbin/skopos-warden-quality rebind 4f08c5c5c617…   # or back to fdb74875531b as before
    docker image tag <that id> histor:warden-remediation-base

Labels the new code issued stay in the log; they are valid signed labels.

## Not done

- 2,000 stdio packages without a digest are rerun only on a new version; a controlled sandbox rerun is needed to
  digest them now (CPU on hunt and PingBlip). Remote servers (3,163) get digests as the 6-hour schedule reaches them.
- The security session's `admin-vps-state-final.json` records the previous image (4f08c5c5c617).
- WARDEN with the MTL/1.1 digest is not released to npm.
