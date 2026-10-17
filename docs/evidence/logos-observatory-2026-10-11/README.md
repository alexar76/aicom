# LOGOS Observatory — production UI refresh

Published at https://logos.modelmarket.dev/ on 2026-10-11.

## Scope

The working LOGOS dashboard now shares the ecosystem's local Inter / Space Grotesk / JetBrains Mono typography and a quieter green, ink and paper palette. A fixed desktop navigation rail replaces the wrapping pill header; mobile retains an explicit menu. All decorative emoji controls were replaced by one local SVG icon family, including copy, refresh, invoke, microphone, export, theme and scene close. No new runtime dependencies or external font requests.

All six working views remain: Insights, Analytics, Daily Briefing, Consumption, NEXUS and Assistant. Five locales and both themes remain. English is the default for new visitors; an explicitly saved language is respected. Public screenshots are English.

The existing observed-data 3D graph is promoted into the first screen. Auto-rotation, pointer orbit, hover, selection and live source data remain. Overlapping labels now appear on inspection. An additional native node selector exposes every observed node and its detail panel to keyboard and touch users. ResizeObserver keeps rendering and projected labels aligned with the available panel size. Node names use textContent rather than HTML interpolation.

## Verification performed

- TypeScript + Vite production build passed; `git diff --check` passed.
- Desktop light/dark inspection, all six views on the live site, no captured browser console errors.
- Mobile 390×844 viewport (375 CSS px content width with scrollbar): menu selection, analytics, no document horizontal overflow in EN/RU/ES/FR/ZH.
- Real federation-overview query succeeded: 18/18 healthy hubs, 221 capabilities, 217 federated capabilities at the time of the check.
- Analytics sorting and anomaly group collapse worked; daily briefing and measured consumption loaded.
- CSV export downloaded successfully as `logos-consumption.csv`.
- NEXUS catalog contained 221 entries; search, selection and invalid-JSON feedback worked.
- Real free `logos.federation.summary@v1` invoke reached the existing backend but failed in its Hub route with HTTP 400. Reproduced directly against production **before** deployment; recorded in `nexus-existing-route-error.json`. No paid invocation was made. **Resolved in the subsequent [NEXUS route fix](../logos-nexus-route-2026-10-11/README.md)**: the production API and browser Invoke now return the real result successfully.
- 3D pointer drag changed projected node positions; the full node selector opened real source status, latency and capability details. Close worked. No pause control was added.
- Assistant input and voice controls remain; no new microphone permission or LLM response test was performed in this change. Anomaly acknowledgement was preserved but not executed against real alerts.
- `production-checks.json` records HTTP results and byte-for-byte comparison of production entry JS/CSS with the built assets.

## Deployment and rollback

The frontend was built locally. Static release: `/var/www/logos-observatory-20261011` on the existing LOGOS host. The edge nginx serves the new root document and assets; API, SSE, health and agent-discovery routes remain on the running LOGOS container. Its container ID was unchanged before/after publication. No environment, signing keys, PostgreSQL, volumes or backend code was changed.

Old hashed assets remain in the release for visitors with an already-open tab. Index HTML is revalidated. Sources build through the existing Dockerfile as before; the next full deployment includes the new UI.

Deployment script: `deploy-ui.sh`. Remote backup and rollback script: `/root/logos-observatory-20261011/`. Run `bash /root/logos-observatory-20261011/rollback-ui.sh` on that host to return the edge configuration to the preceding container-served UI.

Screenshots: `production-insights-light.jpg`, `production-analytics-dark.jpg`.
