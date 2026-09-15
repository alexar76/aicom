# UI screenshots

This folder holds **real PNG** screenshots of the Admin Panel and public pages used in [`../../README.md`](../../README.md), [`../../admin-guide.md`](../../admin-guide.md), and [`../../USER_GUIDE.md`](../../USER_GUIDE.md).

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
- logs in with `ADMIN_PASSWORD` (must match your instance bootstrap password — not a shipped default).

Example with another host:

```bash
DOCS_SCREENSHOT_BASE_URL=http://modeldev.modelmarket.dev:9080 npm run capture-admin-dashboard
DOCS_SCREENSHOT_BASE_URL=http://localhost:9080 ADMIN_PASSWORD='your-admin-password' npm run capture-docs-screenshots
```

> Sidebar tab indices follow `AdminSidebar.tsx` (see comments in the script). Re-check indices if new admin tabs are inserted.

## File names

| File | Content |
|------|---------|
| `public-home.png` | Storefront `/` |
| `public-docs.png` | Public documentation `/docs` |
| `admin-login.png` | `/admin/login` |
| `admin-dashboard.png` | Dashboard after login |
| `admin-sidebar.png` | Same session, `fullPage` (nav column visible) |
| `admin-setup.png` | Setup wizard tab |
| `admin-live-monitor.png` | Live Monitor tab |
| `admin-pipeline.png` | Pipeline tab |
| `admin-new-product.png` | New product wizard |
| `admin-workshop.png` | Workshop tab |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery tab |
| `admin-settings.png` | Settings tab |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |
| `public-blog.png` | Public blog page (legacy capture) |
| `public-launch-kit.png` | Public launch-kit page |
| `public-badge.png` | Public embeddable badge page |
| `account-referral-dashboard.png` | Account referral dashboard |

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

## Last refresh

- Date: 2026-06-24
- Command: `cd web/frontend && node scripts/capture-admin-tabs-only.mjs` (+ restore `admin-providers.png` / `admin-llm-logs.png` from commit `ce9ab272` — live demo returns HTTP 500 on those APIs)
- Source: live demo `http://modeldev.modelmarket.dev:9080` (admin login required in shared environments — set `ADMIN_PASSWORD` to your instance bootstrap password, EN locale, waits for KPI numbers)
- Browser engine: Playwright + system Chrome
