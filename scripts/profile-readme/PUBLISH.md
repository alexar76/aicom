# Publish GitHub profile README (`alexar76/alexar76`)

Canonical source: **`README.md` in this folder** (same file you are reading from the monorepo).

## One-time setup

1. Log in as **@alexar76** on GitHub.
2. Create a **new public** repository named exactly **`alexar76`** (same as your username).
   - Add a README on create, or start empty.
3. Replace the repo’s root `README.md` with the contents of  
   `scripts/profile-readme/README.md` from the monorepo (or copy from Gitea `Superowner/aicom`),
   **copy all `README.{ru,es,fr,zh}.md` language portals**,
   **and copy the `assets/` folder** (hero images are referenced by raw URL — without them the
   profile shows broken images: `alien-monitor-hero.png`, `oracles-hero.gif`).

```bash
# From a machine with push access to github.com/alexar76/alexar76
git clone https://github.com/alexar76/alexar76.git
cd alexar76
cp /path/to/aicom/scripts/profile-readme/README.md ./README.md
cp /path/to/aicom/scripts/profile-readme/README.{ru,es,fr,zh}.md ./
cp -R /path/to/aicom/scripts/profile-readme/assets ./assets   # alien-monitor-hero.png + oracles-hero.gif
git add README.md README.*.md assets
git commit -m "profile: Alien Monitor ecosystem hero + start-here CTAs"
git push origin main
```

4. Open https://github.com/alexar76 — the README should render on your profile within ~1 minute.

## Re-sync after edits

Whenever you change `scripts/profile-readme/README.md` **or anything in `assets/`** in the monorepo, repeat the copy + commit + push to `alexar76/alexar76` only (no mirror script — this repo is special per `satellite-map.yaml` → `export_profile()`).

## Optional profile fields (GitHub → Settings → Profile)

| Field | Suggested value |
| --- | --- |
| Bio | `infrastructure for AI agent economy` |
| Website | `https://magic-ai-factory.com` |
| X (Twitter) | `https://x.com/build_ai_infra` — also linked in README header |
| Pinned repos | Prefer `aicom`, `alien-monitor`, `themis`, `metis`, `aimarket-mcp`, `aimarket-oracle-gateway`, `oracles` (swap out crypto-heavy `acex` / `lottery` for newcomers) |

## Verify

- [ ] Language bar EN · RU · ES · FR · ZH appears under the tagline
- [ ] https://github.com/alexar76 first screen is **Playground · Alien Monitor · School** (no `git clone` above the fold), then the heroes + ecosystem SVG, then a 5-row audience table, then repo catalog
- [ ] `https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png` loads (no 404)
- [ ] `https://raw.githubusercontent.com/alexar76/alexar76/main/assets/oracles-hero.gif` loads (no 404)
- [ ] Links open: magic-ai-factory.com, modeldev.modelmarket.dev, x.com/build_ai_infra, modelmarket.dev, youtu.be/Gg9a52-ZbNA
- [ ] No links to `aicom/tree/main/<satellite>` (those 404 after the split)
