# Agent collaboration story — 2026-10-11

## Published story

The ecosystem landing now leads with **Your AI doesn’t have to do it all.** It introduces specialised agents working together through AIMarket. The factory landing retains its product-building promise, adds the shared message on the first screen, and links directly to the specialist example.

Both pages tell the same explicitly illustrative story: a business dashboard works with sample data but fails on an empty customer list; AICOM requests a bounded diagnosis through AIMarket; a specialist identifies a division-by-zero defect; AICOM validates the report, uses it in the next repair attempt and reruns the original checks. The example does not imply that a complete customer product repair was observed.

A collapsed “What is already verified?” section explains the evidence: a production purchase using Hub credits, an operator-owned provider and a signed diagnostic report for a synthetic defect. The factory guide remains downloadable from that section. Source: [production procurement verification](../procurement-production-2026-10-11/README.md).

English is the default. Copy and visitor-journey documentation were updated in EN, RU, ES, FR and ZH. Screenshots are English.

## Preservation and checks

- All original section anchors and nine ecosystem project cards are preserved (`preservation.json`).
- Existing 3D scene code, motion and keyboard/pointer interaction are unchanged; both scenes rendered in the browser.
- The working factory, backend, catalog records, ordering flows, video disclosure and generator are outside this deployment.
- TypeScript and the five-language static-page validator passed; production Next.js build passed.
- Desktop and 390-pixel mobile views were checked. No document overflow: ecosystem 375/390 px, factory 379/390 px. French factory copy and four example steps rendered after using the language selector.
- The project filter still shows four Trust & verify entries. Both evidence disclosures open.
- The live visitor path was followed: ecosystem story → factory specialist example → working factory.
- `live-checks.json` records all ten localized pages, canonical URLs, links and the working catalog totals. Factory content has the correct server-rendered main language; its existing DocumentLang component sets the document language in the browser.

## Deployment

Only the factory marketing route changed from port 9091 to 9095. Container: `aicom-frontend-collaboration-marketing-20261011`. The working factory stays on `aicom-frontend-catalog-shelves-20261011`, port 9094.

Ecosystem symlink: `/var/www/ecosystem.modelmarket.dev` → `/var/www/ecosystem-collaboration-20261011`. Prior target `/var/www/ecosystem-visitor-20261011` is retained, as is the previous marketing container.

Remote release: `/root/aicom-collaboration-20261011/`. Run its `rollback.py` to restore the prior marketing config and static symlink. Environment values stay in a protected server file and are not committed.

Source publication uses `scripts/push_gitea_monorepo.sh` only; no GitHub publication.
