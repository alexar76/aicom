# Three-domain production split — 2026-10-11

- Working factory and storefront: https://magic-ai-factory.com/
- Factory marketing landing: https://modeldev.modelmarket.dev/
- Canonical ecosystem atlas: https://ecosystem.modelmarket.dev/

The factory landing’s primary button was clicked in the browser and opened the actual application: both the guest generator and product storefront were present, and the marketing page was absent. Returning to the landing reloaded its WebGL scene. The ecosystem “Meet the factory” link points to the factory landing; project cards still open actual services.

All ten public language pages returned HTTP 200 with matching canonical URLs. Language switching was exercised in the browser. Both scenes loaded without console errors and responded to dragging; pause/play controls are absent. Screenshots are `factory-landing.png` and `ecosystem.png`.

The five legacy section entry pages (encyclopedia, school, guides, learn, oracles) were fetched over HTTPS and compared byte-for-byte with their preserved static files. The app root, generator entry and storefront are restored. All four relevant containers are healthy and procurement is enabled; its services were not restarted by this migration. See `verification.json` for recorded checks.

Next.js production build, TypeScript and five-language static-atlas validation passed. The private server-side `AICOM_SITE_ROLE=factory-landing` flag separates the marketing frontend from ordinary app builds; the latter retain the working storefront. Marketing-only language routes reject requests in the ordinary app role. Sources and five-language operating documentation are persisted in the local and server repositories, with server backups.

New-domain DNS propagation initially caused two certificate validation failures. After DNS caches updated, issuance succeeded. The certificate expires 2027-01-09; the existing Certbot timer and nginx deploy hook handle renewal. No certificate validation was disabled. Production has valid HTTPS on all three domains.

Runtime: `aicom-app-1` exposes the working frontend on loopback 9080; `aicom-frontend-modeldev-20261011` uses image `ai-factory-frontend:modeldev-final-20261011` on 9088. The ecosystem static root `/var/www/ecosystem.modelmarket.dev` points to `/var/www/ecosystem-atlas-20261011`. Release scripts and protected backups are in `/root/domain-split-20261011/`; `rollback-modeldev.sh` restores the prior modeldev configuration. Previous frontend releases are retained for recovery.

No GitHub push was performed. The existing GitHub Pages redirect therefore still points to modeldev until a separately authorized publication; the prepared source now declares ecosystem.modelmarket.dev as canonical.
