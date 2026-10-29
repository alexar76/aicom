# Vulnetix fixes of 2026-10-28: production rollout, 2026-10-29

The 2026-10-28 fixes (85db7deea, e35551666) were on PyPI but not in production: every service
below still ran its `main-20261025` image. Each container was replaced with an image built FROM
the running one plus only the fixed files from main 7c4414578, after checking that every live
copy of those files was the pre-fix version (85db7deea^). Tool: `/root/audit-20261025/rollout_container.py`
(health check, automatic rollback, previous container kept stopped as `NAME-security-prev-STAMP`).

The targeted fixes reached all 12 service containers in this rollout: the nine in the table
below and the three MOMUS containers described later. Only momus-backend, momus-treasury and
momus-verifier received the complete `oracle_core` 0.6.3 package. The other nine received the
component files listed below; four of them use `oracle_core` and received only its fixed
`app.py` and `tiers.py`. This is a count of patched containers, not of full 0.6.3 installations.

| host | container | files | setting added |
|---|---|---|---|
| admin-vps | oracles-chronos-1, oracles-oracle-family-1 | oracle_core/app.py, tiers.py | `ORACLE_TRUSTED_PROXIES=127.0.0.1/32,::1/128,gateway` |
| admin-vps | logos | logos/__init__.py, app.py, main.py | none: its own nginx reaches uvicorn over loopback, which now binds 127.0.0.1 |
| admin-vps | platon-platon-backend | platon/main.py | `PLATON_TRUSTED_PROXIES=127.0.0.1/32,::1/128,platon-frontend` |
| admin-vps | skopos-remediation | skopos app_auth, auth_store, client_ip, remediation/git_push | none: it keys nothing on client addresses |
| factory-vps | atlas-atlas-1 | atlas/__init__.py, main.py, serve.py | `ATLAS_TRUSTED_PROXIES=127.0.0.1/32,::1/128,gateway` |
| factory-vps | emporion (SYMMARTYS) | oracle_core/app.py, tiers.py | `ORACLE_TRUSTED_PROXIES=127.0.0.1/32,::1/128,gateway` |
| attested | gaia-gaia-backend-1 | oracle_core/app.py, tiers.py | `ORACLE_TRUSTED_PROXIES=127.0.0.1/32,::1/128,gateway` |
| skopos-vps | metis-skopos | skopos app_auth, auth_store, client_ip, remediation/git_push, locales/*.yaml | `SKOPOS_TRUSTED_PROXIES=127.0.0.1/32,::1/128,metis-nginx,gateway` |

oracle_core's `_signing_key_storage.py` and `__init__.py` were left as they were: the first is
unrelated to these findings and fails closed on quarantined keys, and the second would claim 0.6.3.
The later live check still reports 0.6.1 for chronos and oracle-family, consistent with those
targeted file replacements; see [runtime-checks.json](../vulnetix-response-check-2026-10-29/live-audit-0642/runtime-checks.json).

Each `gateway` was checked against the peer the container actually sees (uvicorn access log or
/proc/net/tcp): the host's nginx arrives through the default route in every case but SKOPOS.
The SKOPOS dashboard sits behind metis-nginx, a container on metisnet that terminates TLS on
80/443, so with `gateway` alone every browser would have shared one login budget. The repo's
gaia, symmartys and metis/deploy/skopos-test compose files now carry the same settings.

Downtime: GAIA starts in about 85 s, close to the tool's 90 s wait. The first replacement timed out
and rolled back by itself. The second, with a 300 s wait (copy in /root/vx-20261029/ on attested),
succeeded. GAIA was down about 3.5 min, then 1.5 min (04:13–04:17Z and 04:18–04:20Z). The others
restarted within seconds.

## MOMUS and its treasury, later the same day

momus-backend and momus-treasury (admin-vps) ran July's oracle-core (4e6e05a0a), whose
`client_key` took X-Real-IP from any caller. A full rebuild from main would also have changed
MOMUS's economics, settlement and engine files, and two live files (remediation.py,
engine/capabilities.py) exist only in the host's build tree. So the image is again the running
one, this time with main's whole `oracle_core` package (0.6.3, 12 files) in place of the old 8.
The live MOMUS and treasury code imports nothing that 0.6.3 lacks. The call log and price gate
stay off because neither `ORACLE_CALLS` nor `ORACLE_TRUSTED_HUBS` is set.

0.6.3 loads signing identities through `_signing_key_storage`, which refuses a symlinked,
hardlinked or quarantined key. Before the swap, every key on the three data volumes was loaded
with the new code in a container with no network and the volume mounted read-only. Each one
printed only ok or FAIL, and all were ok (MOMUS, verifier and treasury, PQC included).

| container | setting added | outside check |
|---|---|---|
| momus-backend | `ORACLE_TRUSTED_PROXIES=127.0.0.1/32,::1/128,momus-frontend,gateway` | /health, /findings, /ai-market/v2/manifest, /warden/threat-feed/summary 200 |
| momus-treasury | `ORACLE_TRUSTED_PROXIES=127.0.0.1/32,::1/128,gateway` | /treasury/health 200 |

momus-frontend is in the list because the public path is host nginx → momus-frontend (nginx,
`X-Real-IP $http_x_real_ip`) → momus-backend. Direct callers on the docker network (logos) are
now keyed by their own address. The compose tag `momus:native-quality-20261010`, which had no
image behind it (so `docker compose up` would have rebuilt MOMUS from the old host tree), and
`momus-deploy-momus-treasury:latest` now point at the patched images.

momus-verifier, the second MOMUS instance that only momus-backend calls, followed at 05:56Z on
the owner's separate go-ahead. Same image recipe, keys checked the same way, no proxy setting:
nothing sits in front of it. It has no published port, so its health was checked from inside it
(200 before and after) and from momus-backend (200). `momus-deploy-momus-verifier:latest` now points
at the patched image. The treasury's own
service.py is still August's. With `TREASURY_CLIENT_TOKEN` set and `AIFACTORY_PROD=1`, the
2026-10-28 keyless change does not apply to it.

The hub's paid-tier header (goal 6, aimarket-hub 3.16.1) is not live: the hubs run 3.16.0, and
no oracle has a paid-tier secret configured.

## Rollback

On the host: `python3 /root/audit-20261025/rollout_container.py NAME --image REPO:pre-vx-20261029 --health URL`,
retag the compose tag (`REPO:latest`, `skopos:shared-ssh-quality-20261010` for remediation,
`momus:native-quality-20261010` for MOMUS) to `REPO:pre-vx-20261029`, and restore `docker-compose.yml.pre-vx-20261029` next to the compose
file. Build contexts and logs are in `/root/vx-20261029/` on each host, and inspect snapshots in
`/root/security-rollbacks/`.
