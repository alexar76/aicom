# aimarket-hub 3.20.0 on all six hubs — 2026-11-11

Owner: «Да, выкатывай» (after «Да, переноси»: the receipt binding brought into main). Times are UTC.

**What went live:** the release wheel `aimarket_hub-3.20.0-py3-none-any.whl` (sha256 e5001655…, built from main 7475d0eef,
every file checked against git), `aimarket-provenance` 2.3.2 where the image had the plugin, fastapi 0.162.4 / starlette
1.10.0 (what 3.20.0 declares; the hub suite passed on them: 4125 passed, 2 known `test_mcp_stdio` fd flakes), and on
Independent cryptography 50.0.2. It carries the 2026-11-11 money-flow audit fixes (migrations 068, 069), the receipt
binding (§7.3.9) with its review fixes, and everything main gathered since the hubs' 3.16/3.17 overlays.

**Before:** every overlay live on the hubs since 2026-11-06 was checked against main by content (12 rollout records):
all of it is in main, so nothing was reverted. modelmarket.dev had lost the receipt binding in an earlier redeploy.

## Per hub

| hub | host / unit | new image or venv | previous (rollback) | DB backup | migrations |
|---|---|---|---|---|---|
| hub.modelmarket.dev (lab, canary) 17:34Z | competing-lab `modelmarket-hub` | `modelmarket-hub:3.20.0-20261111` | `modelmarket-hub-security-prev-1794418490716017497` (image `hub320-base-modelmarket-hub:20261111`) | `/root/hub-backups/modelmarket-hub-pre-3200-20261111T173450Z.db` | +61 62 65 67 68 69 |
| hunt.modelmarket.dev 17:35Z | competing-lab `signal-hunt-hub-1` (PG) | `signal-hunt-hub:3.20.0-20261111` | `signal-hunt-hub-1-security-prev-1794418551827522724` (detached from Compose) | `/root/hub-backups/signal-hunt-hub-1-pre-3200-20261111T173551Z.dump` | same |
| uni.modelmarket.dev 17:36Z | factory-vps `modelmarket-hub-uni` | `modelmarket-hub-uni:3.20.0-20261111` | `modelmarket-hub-uni-security-prev-1794418587874187589` | `/root/hub-backups/modelmarket-hub-uni-pre-3200-20261111T173626Z.db` | same |
| hub.attestedmemory.net 17:37Z | attested `attested-memory-hub-hub-1` (PG) | `attested-memory-hub:3.20.0-20261111` (KEEP_UI: Attested's own navigation) | `attested-memory-hub-hub-1-security-prev-1794418622105580417` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3200-20261111T173701Z.dump` | same |
| modelmarket.dev (apex) 17:37Z | factory-vps `modelmarket-hub` + THEMIS in its netns | `modelmarket-hub:3.20.0-20261111` | `modelmarket-hub-security-prev-1794418666090201945`, `themis-security-prev-1794418666090201945` | `/root/hub-backups/modelmarket-hub-pre-3200-20261111T173745Z.db` | +65 68 69 |
| independentai.network/hub 17:40Z | indep `independentai-hub.service` | venv `/opt/independentai/venvs/hub-3.20.0-20261111`, drop-in `99e-hub-3200-20261111.conf` | delete that drop-in → `hub-3.16.0-rpc-security-20261031` | `/var/backups/independentai/hub-pre-3200-20261111T174052Z.dump` | +61 62 65 67 68 69 |

Rollback of a container hub: `python3 /root/hub-3.20.0-rollout-20261111/kit/rollout_container.py <name> --image
<previous image> --health <url>` or start the `*-security-prev-*` container in place of the new one (the tool's own
restore path). The old code was proven to start and serve on each MIGRATED database copy (smoke `old` mode), so the
additive migrations do not block a rollback. Independent: `./indep320.sh rollback`.

## Checks

- Before each swap, on a copy of that hub's live DB (SQLite online backup; Postgres pg_dump into a throw-away Postgres on
  an `--internal` network, or a temp database on Independent): the new image migrated to 069 with no existing rows
  changed (migration 062 froze no account: no refunded/disputed card top-ups anywhere), health, discovery, peers,
  manifest, search, `/`, `/receipts/verify` (pq_pinned present) and a malformed nonce → 400; then the running image on the
  migrated copy (rollback). `kit/smoke_db.py`, `smoke_sqlite.sh`, `smoke_pg.sh`, `indep320.sh smoke`.
- After: `logs/pubstate-before.jsonl` vs `logs/pubstate-after.jsonl` — all six on 3.20.0, catalogue and peer counts
  unchanged, a free routed invoke with `X-Client-Nonce` carries `receipt_binding` + echo on five of six (UNI does not list
  the test capability, before or after) and `/receipts/verify` says binding valid; modelmarket.dev has the binding again.
  0 restarts, 0 tracebacks in 10 min; THEMIS healthy; ARD 200; MCP initialize OK; a paid route answers 402 with
  `PAYMENT-REQUIRED` exposed; Attested's navigation kept; the apex-only line only on apex.
- Independent's first start released one stale seller-direct x402 claim left by a dead call (an audit fix doing its job).

## Not done here

- PyPI: hub 3.20.0, provenance 2.3.2, treasury 0.1.5, histor 0.9.0 — owner/colleague (§97, folder pypi-release-2026-11-11c).
- `/clients` still offers the 3.16.0 client bundle kept from the images; refresh after 3.20.0 is on PyPI.
- Gitea push of main — owner's word.
