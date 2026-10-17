# LOGOS NEXUS route fix

Published at https://logos.modelmarket.dev/ on 2026-10-11. The previously recorded HTTP 400 for the free federation-summary invocation is resolved.

## Cause and behavior

The NEXUS catalog discarded `product_id` and `source_hub`. Its invoke proxy guessed a product ID from the capability name and omitted the provider. The Hub consequently treated a federated service as local and refused the request with HTTP 400.

The catalog, picker and invocation now retain the full `(product_id, capability_id, source_hub)` identity. Providers offering the same capability remain separately selectable. The backend resolves the exact route against the current Hub manifest; stale routes return 404, and ambiguous legacy requests return 409 instead of silently choosing a provider. Older callers supplying only a capability still work when the route is unique.

The browser sends the displayed price as `max_price_usd`; zero is preserved. Hub failures retain their HTTP status and useful error text. JSON validation and the existing read-only capability restriction remain enforced. Outbound requests go to the configured Hub, never directly to an arbitrary URL supplied by the caller.

## Verification

- `.venv/bin/python -m pytest logos/tests/test_nexus_routes.py logos/tests/test_app.py -q`: **45 passed**. Covers federated and local routes, duplicate providers, legacy calls, stale routes, input validation, price ceiling, upstream failure and the mutation guard.
- `npm --prefix logos/frontend run build`: TypeScript and Vite build passed. The existing lazy Three.js chunk produces its size advisory.
- `git diff --check` and shell syntax checks passed.
- `check-production.py`: real HTTPS call through **LOGOS**, with `prod-logos`, `logos.federation.summary@v1`, `https://logos.modelmarket.dev`, input `{}`, and `max_price_usd: 0`. **HTTP 200**, `status: ok`, `result.ok: true`, price **$0**. Observed 18 healthy hubs and 221 indexed capabilities. The script refuses a route whose catalog price is nonzero.
- Browser: open NEXUS, search the live catalog, select the free LOGOS summary, press Invoke. The actual result appeared with the $0 badge and Hub route. No captured console errors. See `browser-result.json` and `production-nexus-success.jpg` (English interface).
- Production health, index, catalog and referenced JS/CSS returned 200. Entry assets matched the local build byte for byte; hashes and API response are in `production-checks.json`.

No paid service was invoked in this repair. The verified success is the public free summary route; it is not a claim that every catalog service has been individually exercised.

## Deployment and recovery

The existing LOGOS host runs the same container, configuration, signing keys, PostgreSQL and persistent volumes. The backend file and container UI were updated; a derived image `logos-nexus-route:20261011` was built and also tagged `logos-logos` for future recreation. Server build sources were updated. The edge serves `/var/www/logos-nexus-route-20261011`, retaining old hashed assets for already-open tabs.

The first deployment's 30-second readiness gate was too short for historical analytics warmup and triggered an automatic rollback. The resumed deployment allowed 120 attempts and passed on attempt 34. It then switched the edge release; nginx configuration validation passed. `deploy.sh` now uses the corrected readiness window. `resume-deploy.sh` documents the successful resumption without overwriting the original backups.

Remote release workspace and backups: `/root/logos-nexus-route-20261011`. Roll back on that host with `bash /root/logos-nexus-route-20261011/rollback.sh`; allow approximately 35 seconds for analytics warmup before checking `/health`. The previous static release, source archive and original image remain available.

Backend SHA-256 after deployment: `066f16eb31522309f81ae18cf5fd5099e87aa8d02c431dca57af3d8929dbb907`.
