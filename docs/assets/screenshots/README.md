# UI screenshots

This folder holds **real PNG** screenshots of the Admin Panel used in [`../../README.md`](../../README.md) and [`../../admin-guide.md`](../../admin-guide.md).

## Automatic refresh (recommended)

From **`web/frontend`** while the app is **running** (pages reachable, admin password matches config):

```bash
cd web/frontend
npx playwright install chromium   # once per machine
npm run capture-docs-screenshots
```

The script [`../../../web/frontend/scripts/capture-docs-screenshots.mjs`](../../../web/frontend/scripts/capture-docs-screenshots.mjs):

- writes files to **`docs/assets/screenshots/`** (AI-Factory repo root);
- **also copies** every PNG to **`web/frontend/public/docs-screenshots/`** so the `/docs` Next.js page can embed them;
- opens `DOCS_SCREENSHOT_BASE_URL` (default `http://127.0.0.1:9080`);
- logs in with `ADMIN_PASSWORD` (default `admin123`).

Example with another host:

```bash
DOCS_SCREENSHOT_BASE_URL=http://localhost:9080 ADMIN_PASSWORD=admin123 npm run capture-docs-screenshots
```

> By default the sidebar is **collapsed** (icons only): the script switches tabs in order via `aside nav` buttons, not by label text.

## File names

| File | Content |
|------|---------|
| `admin-login.png` | `/admin/login` |
| `admin-dashboard.png` | Dashboard after login |
| `admin-sidebar.png` | Same page, `fullPage` (nav column visible) |
| `admin-pipeline.png` | Pipeline Monitor |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |
| `admin-discovery.png` | Discovery Queue tab |
| `public-blog.png` | Public blog page |
| `public-launch-kit.png` | Public launch-kit page |
| `public-badge.png` | Public embeddable badge page |
| `account-referral-dashboard.png` | Account referral dashboard |

## Coverage note for new UI

New growth and discovery surfaces are now captured. Re-run capture after major UI changes.

## Manual capture

For a single frame without the full script:

```bash
cd web/frontend
npx playwright screenshot http://127.0.0.1:9080/admin/login ../../docs/assets/screenshots/admin-login.png
```

## Embedding in Markdown

```markdown
![Description](./admin-dashboard.png)
```

Paths are relative to the Markdown file under `docs/`.

If you need to refresh screenshots, re-run the capture script above.

## Last refresh

- Date: 2026-05-09
- Environment: `docker compose` stack, `app` healthy on `http://127.0.0.1:9080`
- Command:
  - `npm run capture-docs-screenshots`
- Browser engine: Playwright Chromium (`npx playwright install chromium`)
