# Observed sellers, HEAD first: rollout on all six hubs — 2026-11-01

Owner: «выкатываем на хабы». Code: aicom 5c5a27906 (`aimarket_hub/observed_sellers.py`; on main and Gitea main
since 10-31). The probe sends HEAD first. A 402 whose terms are in the x402 V2 `PAYMENT-REQUIRED` header is the
observation, and no second request goes out. A 2xx to HEAD is `not_priced`, also with no second request. A 404,
405, 400, 422 or 501, or a 402 without header terms, falls back to the one unpaid request of spec §2.7.

All times are server clocks (UTC).

## One file, same baseline everywhere

Before the roll, all six hubs ran the same `observed_sellers.py` (sha256 13a5c7bb42d0, the parent of 5c5a27906).
`outbound_http.safe_request_capped` and `federation_assay.x402_header_offer` were present in every one, so the
overlay is that single file (00e29ab87ab4) and needs no porting. `tests/test_observed_sellers.py` passed on main
(53).

The overlay images were built FROM each hub's running image: the security session's
`aicom-security:*-hc-live-20261031` images, whose OS updates are kept. The `Dockerfile` here has one COPY.
`build.sh` ran `smoke.py` inside each image with no network, then compared the file in the image with the
context. The smoke covers three cases:

- **A seller that answers HEAD with a V2 402.** It goes through consent, `/search`, the well-known, MCP
  `market_search` and DELETE. Its route sees only the HEAD.
- **HEAD 405.** The probe falls back to one POST, and the route is quoted.
- **HEAD 200.** The route is `not_priced`, with one request.

In none of the three cases does a request carry a payment header.

Those images also carry the live container's environment (on UNI as empty strings, which `int()` refuses). So the
smoke drops every hub variable and runs on defaults in a temp dir.

## Hubs

| Hub | Host | Before (rollback image) | After | Rollback container | DB backup |
|---|---|---|---|---|---|
| modelmarket.dev | factory-vps | `aicom-security:modelmarket-hub-hc-live-20261031` | `modelmarket-hub:hf-20261101` | `modelmarket-hub-security-prev-1793512329740430211` (+ `themis-security-prev-1793512329740430211`) | `/app/data/hub-backup-pre-3160-20261101T055208Z.db` |
| uni.modelmarket.dev | factory-vps | `aicom-security:modelmarket-hub-uni-hc-live-20261031` | `modelmarket-hub-uni:hf-20261101` | `modelmarket-hub-uni-security-prev-1793512349665495195` | `/app/data/hub-backup-pre-3160-20261101T055228Z.db` |
| hub.modelmarket.dev | competing-lab | `aicom-security:modelmarket-hub-hc-live-20261031` | `modelmarket-hub:hf-20261101` | `modelmarket-hub-security-prev-1793512363239153311` | `/app/data/hub-backup-pre-3160-20261101T055242Z.db` |
| hunt.modelmarket.dev | competing-lab | `aicom-security:signal-hunt-hub-1-hc-live-20261031` | `signal-hunt-hub:hf-20261101` | `signal-hunt-hub-1-security-prev-1793512369377211891` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261101T055248Z.dump` |
| hub.attestedmemory.net | attested | `aicom-security:attested-memory-hub-hub-1-hc-live-20261031` | `attested-memory-hub:hf-20261101` | `attested-memory-hub-hub-1-security-prev-1793512385751560744` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261101T055305Z.dump` |
| independentai.network/hub | indep (venv) | `/root/hf-20261101/backup-observed_sellers.py` (13a5c7bb42d0) | the file in `hub-3.16.0-rpc-security-20261031` | copy the backup back, `systemctl restart independentai-hub` | none needed |

The rolls ran 05:52–05:53Z with `/root/hub-3160-main-20261021/roll.sh`. It backs up the database and runs
`rollout_container.py`, which keeps the old container stopped and rolls back by itself on a failed health check.
Apex was checked on both :9083 and THEMIS :9460/health. Before each roll the script refused to start if an
OS rollout (`rollout_os_candidates.py` / `rollout_container`) was running.

Contexts and logs are in `/root/hf-20261101/` on each host and copied here.

Independent runs from the security session's venv. Its smoke ran on a patched copy of that venv's package
under the venv's Python. Then the file was backed up and replaced, and the service was restarted in a separate
command; it was healthy after about 6 s.

The compose trap still applies: hunt and attested are compose services. `docker compose up` there would recreate
them from the compose image, not from `:hf-20261101`.

## Verified (05:52–05:55Z)

- **All six hubs.** `/ai-market/v2/health` answers 200 from outside, and so does
  `/ai-market/v2/federation/observed-sellers`.
- **The five container hubs** run `:hf-20261101` with the HEAD-first module.
- **Independent** imports the new module from the running venv.
- **Live probe on our own paid route,** from inside the apex container, with no DB write.
  `probe_route` on `https://modelmarket.dev/x402/x402-check` sent exactly one request, `HEAD`. It got a V2 402
  with `PAYMENT-REQUIRED` and quoted $0.003 (3000 atomic USDC) on eip155:8453, payTo
  `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`, `probe_method: HEAD`. Our own gateway already follows the
  HEAD-first rule.

No outside seller is recorded, so no outside route is probed until a seller gives consent.
