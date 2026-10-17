# Launch Kit

AI-Factory launch package for Product Hunt, Show HN, and community posts.

## Language for published materials

Use English for all externally shared posts, campaign images, screenshots, demo videos, captions, narration, and alt text, on every channel. Before capturing a localized interface, select English and use English example content; check the resulting frames as well as the surrounding copy. Russian remains a supported language in documentation and interfaces.

For the working factory, start captures at `https://magic-ai-factory.com/?lang=en`. Use the English root pages of `https://modeldev.modelmarket.dev/` and `https://ecosystem.modelmarket.dev/` for promotional captures. Localized QA evidence is not a publication asset.

**Ops kit:** `../PromoMaterials/aicom/README.md` in the separate local PromoMaterials checkout. From the AICOM repository root, generate UTM links:
`python3 scripts/promo_build_links.py`

**Week 0 (before any launch day):**

- [ ] Honesty pass — demo caps tagged `demo:true`, one oracle count vocabulary (17 / 23 / 35)
- [ ] Factory README links point at satellite repos (not excluded monorepo paths)
- [ ] `python3 scripts/ecosystem_watchdog.py --no-telegram` green on prod URLs
- [ ] `gitleaks` clean via `.github/workflows/security-scan.yml`
- [ ] ToS + Privacy pages live; lottery in explicit demo mode if gambling risk
- [ ] Cron: `scripts/backup_channels.sh` + watchdog every 5–15 min

## Press Kit Essentials

- Product name: AI-Factory
- Tagline: One phrase to launch-ready product assets.
- Core value: discovery + generation + quality gates in one pipeline.
- Proof points: benchmark pass rates, trust block metrics, batch workflow.
- Assets: logo, screenshots, benchmark capture, short demo GIF/video.

## Launch Checklist (Week 2 — one channel first)

- [ ] Generate UTM links → `../PromoMaterials/aicom/utm/generated-links.md`
- [ ] Validate checkout flow and plan upgrades in staging.
- [ ] Confirm referral links are tracked in checkout orders.
- [ ] Hero GIFs in README: `argus-warden` WARDEN block · `aicom-landing` prompt→page
- [ ] Record "10 products in 2 minutes" demo (optional — wedge is landing URL).
- [ ] **Show HN only** — one offer: landing $4.99–9.99 with live URL (~21 min).
- [ ] Prepare maker comment with on-chain journal link + pet-project-trust disclaimer.
- [ ] Reply-game: 10–15 substantive comments/day for 14 days after launch.
- [ ] Publish changelog and support contact link.

## Wedge (recommended)

**Factory landing with live URL** — positive unit economics, `npx aicom-landing`, demo GIF, watermark loop.
Marketplace / oracles — second wave after first external payment signal.
