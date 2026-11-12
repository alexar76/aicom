# Hub 3.21.0 on all six hubs — 2026-11-12

All times are server UTC (the Mac that drove the rollout runs about 58 minutes ahead).

**What went out.** `aimarket-hub` 3.21.0 from local main `ce215c70b` (branch commit `964487d2b`): the catalogue as
an AI Catalog (`/.well-known/ai-catalog.json`, `/ai-catalog/v1/capabilities.json`, signer profiles under
`/ai-catalog/profiles/`), an MCP Server Card in the accepted schema at `/mcp/server-card`, an ML-DSA-65 key in the
DID document. No database migration (highest is still 069).

**The wheel.** `aimarket_hub-3.21.0-py3-none-any.whl`, sha256
`e3dd66ef1dcbf46e52738d06fd3611e2906814d35dba371d23339ac0226fdd09`, built from a clean tree; its 229 files equal
main. Not uploaded to PyPI (a step for the colleague, `docs/distribution/colleague-tasks.md` §101).

## How

The kit in `kit/` (on each host: `/root/hub-3.21.0-rollout-20261112/kit`):

1. `build.sh` builds the new image FROM the image the hub runs; `activate.py` makes `/app/aimarket_hub` the
   wheel's package and keeps the hub's own UI where a hub has one (`KEEP_UI=1` on Attested).
2. `smoke_sqlite.sh` / `smoke_pg.sh` run `smoke_db.py` on a copy of the live database, first with the new image,
   then with the old one on the same copy (the rollback still reads what the new one wrote).
3. `roll.sh` backs the database up and swaps the container with `rollout_container.py`, which puts the previous
   container back when a health URL does not answer. Independent (systemd, no container): `indep321.sh` makes a
   new venv and a drop-in.
4. `logs/pubstate.py` before and after; `logs/verify_live.py` from outside with libraries that are not the hub's
   (rfc8785, cryptography, dilithium-py).

Open alerts were read before the first step: none in the previous 20 hours.

## Per hub

| hub | host, unit | switched | new image | previous (rollback) | database backup |
|---|---|---|---|---|---|
| hub.modelmarket.dev (canary) | competing-lab, `modelmarket-hub` | 12:14Z | `modelmarket-hub:3.21.0-20261112` | container `modelmarket-hub-security-prev-1794485645077010420`; base tag `hub321-base-modelmarket-hub:20261112` | `/root/hub-backups/modelmarket-hub-pre-3210-20261112T121404Z.db` |
| hunt.modelmarket.dev | competing-lab, `signal-hunt-hub-1` (Postgres `signal-hunt-postgres-1`) | 12:16Z | `signal-hunt-hub:3.21.0-20261112` | `signal-hunt-hub-1-security-prev-1794485801066664020` | `/root/hub-backups/signal-hunt-hub-1-pre-3210-20261112T121640Z.dump` |
| uni.modelmarket.dev | factory-vps, `modelmarket-hub-uni` | 12:18Z | `modelmarket-hub-uni:3.21.0-20261112` | `modelmarket-hub-uni-security-prev-1794485936717631685` | `/root/hub-backups/modelmarket-hub-uni-pre-3210-20261112T121855Z.db` |
| modelmarket.dev | factory-vps, `modelmarket-hub` (THEMIS shares its network namespace; health on 9083 and 9460) | 12:20Z | `modelmarket-hub:3.21.0-20261112` | `modelmarket-hub-security-prev-1794486040186403666` | `/root/hub-backups/modelmarket-hub-pre-3210-20261112T122039Z.db` |
| hub.attestedmemory.net | attested, `attested-memory-hub-hub-1` (Postgres `attested-memory-hub-postgres-1`) | 12:24Z | `attested-memory-hub:3.21.0-20261112` | `attested-memory-hub-hub-1-security-prev-1794486243150648763` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3210-20261112T122402Z.dump` |
| independentai.network/hub | indep, `independentai-hub.service` | 12:26Z | venv `/opt/independentai/venvs/hub-3.21.0-20261112`, drop-in `99f-hub-3210-20261112.conf` | `./indep321.sh rollback` removes the drop-in: the 3.20.0 venv again | `/var/backups/independentai/hub-pre-3210-20261112T122658Z.dump` |

**Rollback of a container hub:** `python3 rollout_container.py <container> --rollback` in the kit directory (the
previous container is kept under the name in the table), or start that container by hand after stopping the new
one. Nothing in the databases needs undoing.

## nginx, two hosts

- **hunt.modelmarket.dev** sent the new paths to the game (404). `kit/nginx_hunt.py` added
  `location = /.well-known/ai-catalog.json` and `location ^~ /ai-catalog/` to the hub, and the `Link` header.
  Backup: `/etc/nginx/sites-available/hunt.modelmarket.dev.bak-20261112-aicatalog`.
- **independentai.network**: the hub lives under `/hub`, so the well-known path at the origin answered 404.
  `kit/nginx_indep.py` answers it with a 302 to `/hub/.well-known/ai-catalog.json`.
  Backup: `/root/nginx-backups/independentai.network.bak-20261112-aicatalog`.

Both were applied with `nginx -t` first and a reload.

## Checks

- **Smoke on a copy of each live database:** passed with the new image and with the old image afterwards, on all
  six.
- **From outside (`logs/verify_live.py`):** hub.modelmarket.dev 92 checks, hunt 100, uni 100, modelmarket.dev 124,
  hub.attestedmemory.net 268, independentai.network/hub 132 (with `--unsigned`: a hub under a path has no
  did:web, so its catalogue carries no signatures). Ed25519 Trust Manifests and the ML-DSA-65 signature over each
  document verified on the five hubs that sign.
- **`logs/pubstate-before.jsonl` / `pubstate-after.jsonl`:** every hub 3.20.0 → 3.21.0; offer counts and the test
  invoke unchanged; receipt binding valid (uni answers 404 for the test capability before and after).
- **About 25 minutes later (12:44Z):** every hub answers `/ai-market/v2/health` with 3.21.0; no container has
  restarted (`RestartCount` 0, systemd `NRestarts` 0). Logs: no traceback on five hubs. modelmarket.dev had nine
  5xx answers and one unhandled `ExceptionGroup` (the 500 of `POST /ai-market/v2/p/aimarket-zk/zk/prove-input`)
  from one client walking the OpenAPI paths with their `{placeholders}`; the previous container's log shows the
  same paths with the same answers (283 such answers and 15 of the same exception in its last 24 hours), so this
  is not from 3.21.0.

## Not done here

- PyPI upload of 3.21.0 and the GitHub mirror: the colleague's steps (§101).
- The previous containers and base tags stay until the next release.
