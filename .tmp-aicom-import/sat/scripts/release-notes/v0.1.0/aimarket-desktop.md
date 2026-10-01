## AIMarket Desktop v0.1.0 (early)

**What works today**
- Melos monorepo: Flutter, Tauri, and VS Code integrations for AIMarket
- Apps exported from `desktop-integrations/` (reputation dashboard, IDE helpers, and related SKUs)
- CI: analyze + web build matrix on GitHub Actions

**Unstable / may change**
- App boundaries and package layout between apps
- Dart SDK path/git deps to `aimarket-sdks` — pin by tag when integrating

**Not in this release**
- App Store / notarized desktop distribution; use source builds
