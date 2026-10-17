# Production landing deployment — 2026-10-11

Production URLs:
- Factory: https://magic-ai-factory.com/
- Ecosystem: https://modeldev.modelmarket.dev/ (EN), `/ru/`, `/es/`, `/fr/`, `/zh/`.

Deployed directly to the existing VPS. No GitHub push, merge or Pages publication was performed in this deployment. GitHub Pages remains a separate publishing destination.

## Deployment

Factory image: `ai-factory-frontend:landing-20261011`, digest `sha256:b862551fc2a2f9d407df9cf41185e16145ad7e24f4ceb20b49831e840721a5de`.
Container: `aicom-frontend-landing-20261011`; restart policy `unless-stopped`; loopback `9086 → 8080`; network `aicom_aicom_net`. It uses the existing backend `http://aicom-app-1:8081`. No Docker socket or data volume is mounted into the new frontend. Existing security-header settings were preserved.

Only the generic factory nginx upstream changed from 9080 to 9086. Existing generator, agents, monitor, API and TLS locations were preserved. The combined `aicom-app-1` container was not restarted or replaced; its ID and start time matched before and after deployment. Procurement/backend changes were not deployed or enabled.

Atlas root: `/var/www/modeldev.modelmarket.dev` now points to `/var/www/modeldev-atlas-20261011`. Assets are namespaced under `/ecosystem-atlas/`. Old static sections were compared byte-for-byte and retained; old sitemap URLs are a subset of the merged sitemap. Previous root: `/var/www/modeldev-before-atlas-20261011`.

Release source, Dockerfile, build log, checks, nginx backups and rollback: `/root/landing-release-20261011/` on `factory-vps`. The release folder is the factory frontend deployment source. A future full application deployment must explicitly preserve or replace the separate frontend upstream; rebuilding the old combined app alone will not update the landing.

Rollback both sites:

```sh
ssh factory-vps /root/landing-release-20261011/rollback.sh
```

The script restores the previous static root and nginx configs, validates nginx and reloads it. The old frontend remains running on 9080. Rollback does not require rebuilding images. A first switch was automatically rolled back because the probe reached an old nginx worker during graceful reload; the check was updated to tolerate reload propagation, and the final switch succeeded.

## Validation

- Production image build passed.
- Preflight: five factory locales, API health, lead page, docs, scene/vendor/social resources all returned 200; security headers matched the existing frontend.
- [34 real HTTPS checks](http-checks.json) passed: both sites in five languages, five downloadable guides, API health, lead/docs/agents/generator, 3D resources, sitemap, robots and preserved encyclopedia/learn/school/guides/oracles routes.
- Browser: both actual production pages rendered 3D successfully, no JavaScript errors were captured; factory pause and stage selection worked; the atlas trust filter reduced the visible list from nine to four projects.
- Screenshots: [factory](factory.jpg), [ecosystem](ecosystem.jpg).
- These are landing and read-only API checks. No paid procurement, lead submission, email or new product pipeline was triggered by deployment verification.

Five-language deployment documentation: `docs/landing-separation*.md`.
