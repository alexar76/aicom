# Storefront: $0.99 animated landings (crypto → ZIP)

How to list wow marketing landings at **$0.99 USDT**, buy one on-chain, download a ZIP, and optionally auto-publish to Vercel.

Live demo: [magic-ai-factory.com](https://magic-ai-factory.com) · Hub payments: [modelmarket.dev](https://modelmarket.dev)

## What already works

| Step | Surface |
|------|---------|
| Create landing | Admin `POST /api/admin/products/create` with `delivery_profile: "marketing_landing"` + `style_preset_id` |
| Style presets | `GET /api/public/landing-presets` (aurora-glass, kinetic-type, mesh-gradient-hero, …) |
| Price override | `PATCH /api/admin/pipeline/products/{id}/storefront-pricing` `{ "admin_storefront_usdt": 0.99 }` |
| Crypto checkout | Customer auth → `POST /api/payment/create` → pay USDT/USDC on Base (etc.) → `POST /api/payment/confirm/{id}` |
| Download | `GET /api/customer/orders/{order_id}/download` → ZIP of `data/code/<product_id>/` |
| Auto-publish | `general.auto_publish_*` + `VERCEL_TOKEN` / Netlify / Cloudflare — see [auto-publish.md](auto-publish.md) |

Default catalog price for landings is **~$4.99**; **`$0.99` is the operator override** via `admin_storefront_usdt`.

Crypto is **real on-chain** when `AIFACTORY_CRYPTO_ENABLED=1` and `verify_stub=false` (public demo). Funds settle to `AIMARKET_PAYMENT_RECIPIENT` / `crypto.wallet_addresses.evm` (LIVE: same treasury wallet as hub/deployer — see [onchain-journal.md](onchain-journal.md)).

## Agent / operator recipe (10 landings)

1. Admin login: `POST /api/admin/auth/login` `{ "username": "admin", "password": "" }` on the public demo (passwordless). Send `Authorization: Bearer …` + `X-CSRF-Token` on mutations.
2. Clear focus so the batch is not paused: `POST /api/admin/pipeline/focus-mode` `{ "clear_focus": true, "resume_factory": true }`.
3. Create up to 10 products, each with a distinct `style_preset_id` and instructions that require CSS/SVG motion.
4. Immediately price each: `{ "admin_storefront_usdt": 0.99 }`.
5. Ensure `general.auto_pipeline: true` (on the public demo, Settings save is blocked by `AIFACTORY_DEMO_READONLY` — set the overlay on the host, then restart the app).
6. Wait until `state=COMPLETED` / storefront-visible.
7. Buy: register customer → create payment (amount is server-side from catalog) → send **0.99 USDT (or USDC)** to the invoice address on the chosen chain → confirm with `tx_hash` → download ZIP.

## Auto-publish to Vercel

```yaml
# general.* (Admin Settings or admin_config_overlay.yaml)
auto_publish_enabled: true
auto_publish_landing_only: true
auto_publish_provider: vercel
```

Host env (pipeline worker):

```bash
VERCEL_TOKEN=…          # required
VERCEL_ORG_ID=…         # optional
```

Without `VERCEL_TOKEN`, landings still sell and ZIP-download; they just will not get a `*.vercel.app` URL. Alternatives: Netlify / Cloudflare Pages — [auto-publish.md](auto-publish.md).

**Public demo (2026-08-07):** `VERCEL_TOKEN` + `general.auto_publish_enabled: true` / `auto_publish_provider: vercel` are set on the magic-ai-factory.com host (`.env` + overlay). New landings deploy after DevOps; existing batch can be pushed with `python3 scripts/publish_product_now.py prod-…` inside the app container.

Manual one-off:

```bash
python3 scripts/publish_product_now.py prod-xxxxxxxxxxxx
```

## Batch started 2026-08-07 (demo)

Ten `marketing_landing` SKUs queued on magic-ai-factory.com at **$0.99** checkout override:

| product_id | preset |
|------------|--------|
| `prod-89be3fd38413` | aurora-glass |
| `prod-383f8c5e104f` | kinetic-type |
| `prod-12f13699efd3` | mesh-gradient-hero |
| `prod-491ceb8a448f` | cyberpunk-hud |
| `prod-2849b6c85620` | soft-clay-3d |
| `prod-91aaebe241e2` | northern-lights-ui |
| `prod-61da0a793f22` | luxe-gold-obsidian |
| `prod-8d18982cca83` | phosphor-retro |
| `prod-95c02d0466df` | oceanic-depth |
| `prod-efa9a83a2788` | blossom-pastel |

Pipeline started after enabling `auto_pipeline` on the host overlay. Purchase + ZIP of the first completed SKU is the smoke test for this doc.

## Notes

- Public demo cannot change Settings via API (`AIFACTORY_DEMO_READONLY=1`) — host overlay only.
- Do not use payment stub confirm on production (`AIFACTORY_PAYMENT_VERIFY_STUB=0`).
- Prefer a **buyer** wallet distinct from the treasury recipient for a clean settle proof.
