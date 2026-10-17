# Factory, storefront and ecosystem: three separate addresses

[EN](landing-separation.md) · [RU](landing-separation.ru.md) · [ES](landing-separation.es.md) · [FR](landing-separation.fr.md) · [中文](landing-separation.zh.md)

| Address | Role |
| --- | --- |
| `https://magic-ai-factory.com/` | Working factory, guest generator, product storefront and admin entry |
| `https://modeldev.modelmarket.dev/` | New factory marketing landing, replacing the large mixed landing |
| `https://ecosystem.modelmarket.dev/` | Canonical machine-economy ecosystem atlas |

The factory landing’s primary action opens the working factory. Product links open its storefront at `/#products`; generator, agents, docs and policy links go to the same working application. Ecosystem links go to the separate canonical atlas. The atlas introduces the factory through its marketing page and links project cards to their actual services.

The working factory was restored, not replaced by the marketing page. Procurement remains enabled; its backend, journal, account and budgets are unchanged by this domain split. See [procurement guide](factory-subcontracting.md).

## Implementation

`app/HomePage.tsx` is the working storefront. `components/factory/FactoryLanding.tsx` is the marketing page. Only the separate frontend built and run with `AICOM_SITE_ROLE=factory-landing` renders the marketing page at `/` and `/ru/`, `/es/`, `/fr/`, `/zh/`. Ordinary app builds keep the storefront. The marketing build uses `NEXT_PUBLIC_SITE_URL=https://modeldev.modelmarket.dev`, dedicated metadata and language alternatives; its primary links use the absolute factory address. It does not install the app PWA or market widget.

The atlas source is `scripts/github-io/`; generated pages, sitemap and social metadata use `https://ecosystem.modelmarket.dev`. `ATLAS_SITE_URL` can explicitly override the origin for a separate build. The GitHub repository is not pushed by this release. Its existing hosted redirect stays unchanged until a separately authorized publication.

Both marketing models rotate as complete structures, respond to mouse/touch dragging and arrow keys, and have no pause/play controls. Reduced-motion preferences retain manual control while disabling automatic motion. These are conceptual illustrations, not live telemetry. Existing encyclopedia, school, guides, learn and oracle routes on modeldev remain available.

## Production and verification

The working app remains on loopback 9080. The modeldev frontend uses 9088 and image `ai-factory-frontend:modeldev-final-20261011`; its container is `aicom-frontend-modeldev-20261011`. The atlas root is `/var/www/ecosystem.modelmarket.dev`, pointing to `/var/www/ecosystem-atlas-20261011`. Release sources, protected environment file and backups are in `/root/domain-split-20261011/`; `rollback-modeldev.sh` restores the previous modeldev vhost. Keep the active app and procurement containers running.

HTTPS for the new hostname uses the existing Certbot account, webroot challenge and renewal timer with nginx reload hook. DNS propagation must finish before requesting a certificate. Never replace existing TLS configurations with a bare HTTP template.

Validate the five locales, canonical and alternate links, primary navigation to the actual factory, both draggable WebGL scenes, preserved static sections and API health. Run `npm --prefix web/frontend run typecheck`, the production frontend build, and `python3 scripts/github-io/validate.py`. Proof and final deployment results are in [domain-split evidence](evidence/domain-split-2026-10-11/README.md).
