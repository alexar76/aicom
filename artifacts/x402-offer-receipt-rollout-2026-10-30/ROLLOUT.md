# x402 Offer and Receipt + interop page rollout — 2026-10-30

Owner: «Да, выкатывай» (12:00Z).

## x402 Offer and Receipt (main 84abd9327)

Production runs the pre-split `hub_routes/invoke.py` in two variants (apex vs the other five; `middleware.py`
identical everywhere). The change was ported into the live files: `x402_offer_receipt.py` (new), `api.py`
(`signer=` passed to the middleware), `hub_routes/middleware.py` (offers on the 402), `hub_routes/invoke.py`
(`_x402_settlement` after delivery). Overlay images FROM the running `:rb-20261030` (another session's
receipt-binding overlay); each image ran a smoke test inside itself (402 carries an offer that verifies under the
hub key; settlement receipt verifies; `_x402_settlement` present). Contexts: `/root/or-20261030/` on each host.

| Hub | Host | Before (rollback image) | After | Rollback container | DB backup |
|---|---|---|---|---|---|
| modelmarket.dev | factory-vps | `modelmarket-hub:rb-20261030` | `modelmarket-hub:or-20261030` | `modelmarket-hub-security-prev-1793361625101720122` | `/app/data/hub-backup-pre-3160-20261030T120024Z.db` |
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:rb-20261030` | `modelmarket-hub-uni:or-20261030` | `modelmarket-hub-uni-security-prev-1793361634672102432` | `/app/data/hub-backup-pre-3160-20261030T120033Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:rb-20261030` | `modelmarket-hub:or-20261030` | `modelmarket-hub-security-prev-1793361723937829825` | `/app/data/hub-backup-pre-3160-20261030T120203Z.db` |
| hunt.modelmarket.dev | competing-lab | `modelmarket-hub:rb-20261030` | `modelmarket-hub:or-20261030` | `signal-hunt-hub-1-security-prev-1793361729940328372` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261030T120209Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub:rb-20261030` | `attested-memory-hub:or-20261030` | `attested-memory-hub-hub-1-security-prev-1793361782324737611` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261030T120301Z.dump` |
| independentai.network/hub | indep (venv) | files in `/root/or-20261030/backup-venv/` | four files copied into `hub-3.16.0-rpc` | restore the four files, `rm x402_offer_receipt.py`, `systemctl restart independentai-hub` | none needed (no schema change) |

THEMIS (borrows the apex netns) was recreated by the roll and passed its health check.

Verified from outside (12:05Z): all six `health=ok`. Apex (`weather.witness@v1`) and Attested
(`memory.verify@v1`): the 402's `PAYMENT-REQUIRED` carries `extensions.offer-receipt.info.offers[0]`, an EdDSA JWS
with `kid` = the hub's did:key, verifying under `signer_public_key` from `/.well-known/agent-marketplace`, payTo equal
to `accepts[0].payTo`. UNI, lab, hunt and Independent list no local paid capability, so no 402 to observe there.
Receipts appear only on a real paid call; not exercised in production (no purchase made).

## Interop page

`/etc/nginx/sites-enabled/modelmarket.dev` gained `location ^~ /interop/` (alias `/var/www/interop/`) — backup
`/root/nginx-backups/modelmarket.dev.20261030-115942-before-interop`, `nginx -t` ok, reloaded;
`https://modelmarket.dev/interop/` → 200. The hourly `aimarket-interop.timer` was refused by the auto-mode classifier
at first; on the owner's explicit «Поставь таймер» it was installed at 12:51Z (`aimarket-interop.{service,timer}`, hourly)
and the page regenerated: 2 outside providers pass, 0 outside hubs, 0 outside witnesses.
