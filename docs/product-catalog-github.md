# Factory product catalog (GitHub)

Selective monorepo of **full** factory products under **[alexar76/aicom-products](https://github.com/alexar76/aicom-products)**.

Not every pipeline run is published — only allowlisted product ids, on demand or when Settings → **Product catalog (GitHub)** is enabled after DevOps.

## Layout

```
products/<product_id>/   # full tree (source + docs; no node_modules / .venv / .aicom_sandbox)
```

## Manual publish

**Shell / satellite** (like oracles — preserves `products/`):

```bash
GH_PAT=… ./scripts/publish_all_repos.sh --satellite aicom-products
```

**Selective product tree** from the factory host:

```bash
GH_PAT=… ./scripts/publish_factory_product_catalog.sh \
  --product prod-bdb1634806de \
  --from-factory-host
```

If `data/state/<id>/auto_publish.json` (or `--live-url https://….vercel.app`) has a public HTTPS demo URL, the product `README` gets a **Live:** line and `PRODUCTS.md` links it.

Or with a local checkout:

```bash
GH_PAT=… ./scripts/publish_factory_product_catalog.sh \
  --product prod-XXXXXXXXXXXX \
  --source /path/to/data/code/prod-XXXXXXXXXXXX
```

Remote is fixed to `https://github.com/alexar76/aicom-products.git` (alexar76 + `GH_PAT`). Do not freestyle remotes. Monorepo source shell: `aicom-products/` (excluded from trimmed factory publish).

## Gate

When `product_catalog_require_github_house` is on **and** catalog is enabled **and** `GH_PAT` / `GITHUB_TOKEN` is set on the host:

- root `README.md` with `<!-- aicom-readme-badges -->` (or `docs/badges/`)
- root `CONTRIBUTING.md`

If GitHub is **not** configured (no PAT), the house gate stays **off** and catalog publish is skipped — QA does not fail products for missing CONTRIBUTING/badges. Enabling the catalog toggle in Settings without a PAT returns HTTP 400.

QA `_assess_github_house` also flags missing CONTRIBUTING / badge rows **only when the gate is active**.

## Settings

Admin → Settings → **Product catalog (GitHub)**:

| Key | Meaning |
|-----|---------|
| `product_catalog_enabled` | After DevOps, try catalog push (non-blocking) |
| `product_catalog_allowlist` | Comma-separated `prod-…` ids |
| `product_catalog_require_github_house` | Block catalog push without README badges + CONTRIBUTING |

Also: Sandbox git (`/api/sandbox/git/…`) and **Git remote** settings remain for per-product remotes — catalog is the shared monorepo.
