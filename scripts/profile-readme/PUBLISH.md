# Publish GitHub profile README (`alexar76/alexar76`)

Canonical source: **`README.md` in this folder** (same file you are reading from the monorepo).

## One-time setup

1. Log in as **@alexar76** on GitHub.
2. Create a **new public** repository named exactly **`alexar76`** (same as your username).
   - Add a README on create, or start empty.
3. Replace the repo’s root `README.md` with the contents of  
   `scripts/profile-readme/README.md` from the monorepo (or copy from Gitea `Superowner/aicom`).

```bash
# From a machine with push access to github.com/alexar76/alexar76
git clone https://github.com/alexar76/alexar76.git
cd alexar76
cp /path/to/aicom/scripts/profile-readme/README.md ./README.md
git add README.md
git commit -m "profile: ecosystem map + start-here CTAs"
git push origin main
```

4. Open https://github.com/alexar76 — the README should render on your profile within ~1 minute.

## Re-sync after edits

Whenever you change `scripts/profile-readme/README.md` in the monorepo, repeat the copy + commit + push to `alexar76/alexar76` only (no mirror script — this repo is special per `satellite-map.yaml` → `export_profile()`).

## Optional profile fields (GitHub → Settings → Profile)

| Field | Suggested value |
| --- | --- |
| Bio | `infrastructure for AI agent economy` |
| Website | `https://magic-ai-factory.com` |
| Pinned repos | `aicom`, `aimarket-protocol`, `aimarket-hub`, `aimarket-agent` |

## Verify

- [ ] https://github.com/alexar76 shows the CTA table and ecosystem tables
- [ ] Links open: magic-ai-factory.com, alexar76.github.io/aicom, modelmarket.dev, youtu.be/Gg9a52-ZbNA
- [ ] No links to `aicom/tree/main/<satellite>` (those 404 after the split)
