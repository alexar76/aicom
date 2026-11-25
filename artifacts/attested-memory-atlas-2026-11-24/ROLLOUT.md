# Attested Memory: atlas review fixes on attested, 2026-11-24

Fixes of main 09e18a07c (signer_key + chain_head in Ledger.verify, anonymous memory.attest@v1 refused,
hub write requests a receipt + reconcile_provenance, truth filter on catalog/search) as overlays over the
running images. Host: attested, compose /opt/aicom/attested/attested-memory-hub.

## What runs

| service | image | over |
|---|---|---|
| memory-market | `attested-memory-hub-memory-market:atlas-20261124` (sha256:3dfa83d4…) | `bref-20261104` |
| provenance-ledger | `attested-memory-hub-provenance-ledger:atlas-20261124` (sha256:c69b653c…) | `bref-20261104` |

Only these two were recreated (`docker compose up -d --no-deps memory-market provenance-ledger`). The hub
container runs `attested-memory-hub:3.22.0-capsfix-20261122`, which is NOT what compose names
(`aicom-security:attested-hub-public-20261108t065010z`); it was not touched. Kit: `kit/` here and
`/root/am-atlas-20261124` on the host (Dockerfiles copy the package into site-packages).

## Why overlays, not main

The live packages (in site-packages; `/app/src` in the images is a stale copy) are older than main. Main
also carries, NOT deployed: `actor_auth.py` (request-bound actor proofs, c3e0fa82e 2026-10-25; changes
REST auth for the SaaS gateway and apps), the Ed25519 small-order key check in the ledger's crypto.py
(580e5316c 2026-10-12) and the market db nonce table. Deploying main would ship those auth changes
unreviewed. One older fix WAS taken along: the whole `catalog()` of main, because it is the function the
truth filter lives in. Before this rollout, live search matched the CONTENT of paid memories for callers
who had not bought them (substring probing of paid text); now content is searched only where the caller
may read it, and LIKE metacharacters in team ids are escaped.

## Checks

- Overlay sources tested before the build: memory-market test_store, test_hub_buyer,
  test_truth_and_provenance + all ledger tests, 25 passed (Python 3.12, AIFACTORY_DEV=1).
- Ledger before: 3 receipts, all Ed25519 + ML-DSA keys = the ledger's own (no trusted-key list needed).
- After: both containers healthy; the 3 receipts verify valid with signer_key and chain_head; an internal
  memory.attest@v1 call without a buyer ref → 403; catalog `truth=bogus` → 422; no tracebacks.
- reconcile_provenance: 5 unattested units → 5 attested; ledger 8 receipts, all valid.

## Rollback

```bash
ssh attested 'cd /opt/aicom/attested/attested-memory-hub && cp /root/docker-compose.yml.pre-atlas-20261124 docker-compose.yml && docker compose up -d --no-deps memory-market provenance-ledger'
```

The 5 receipts written by reconcile stay in the ledger (append-only); the old code ignores the checks.
