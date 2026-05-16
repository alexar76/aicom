#!/usr/bin/env node
/**
 * Captures Admin + public UI screenshots into ../../docs/assets/screenshots/
 * Requires: running app (e.g. http://127.0.0.1:9080), default admin password.
 *
 * Usage (from web/frontend):
 *   npx playwright install chromium
 *   node scripts/capture-docs-screenshots.mjs
 *
 * Env:
 *   DOCS_SCREENSHOT_BASE_URL — default http://127.0.0.1:9080
 *   ADMIN_PASSWORD — default admin123
 *
 * Sidebar tab order (see AdminSidebar.tsx, no `users` unless super_admin):
 *   0 Dashboard, 1 Setup wizard, 2 Live Monitor, 3 Pipeline, 4 New product,
 *   5 Workshop, 6 Files, 7 Agents, 8 Providers, 9 LLM logs, 10 Agent logs,
 *   11 Security, 12 Sandbox, 13 Director, 14 Discovery, 15 Settings,
 *   16 Chat, 17 Brainstorming, 18 Support queue, 19 Outreach
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..');
/** Repo root: …/aicom (this file lives in …/aicom/web/frontend/scripts/) */
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '../..');
const OUT = path.join(REPO_ROOT, 'docs/assets/screenshots');

const BASE = process.env.DOCS_SCREENSHOT_BASE_URL || 'http://127.0.0.1:9080';
const PASSWORD = process.env.ADMIN_PASSWORD || 'admin123';

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await delay(600);
  await page.screenshot({ path: path.join(OUT, 'public-home.png'), fullPage: false });

  await page.goto(`${BASE}/docs`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await delay(800);
  await page.screenshot({ path: path.join(OUT, 'public-docs.png'), fullPage: false });

  await page.goto(`${BASE}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await delay(500);
  await page.screenshot({ path: path.join(OUT, 'admin-login.png') });

  const passInput =
    page.getByPlaceholder('Enter admin password').or(page.locator('input[type="password"]'));
  await passInput.fill(PASSWORD);
  await page.getByRole('button', { name: /^Login$/i }).click();
  await page.waitForURL(/\/admin(\?|$)/, { timeout: 45000 });
  await delay(800);

  await page.screenshot({ path: path.join(OUT, 'admin-dashboard.png') });
  await page.screenshot({ path: path.join(OUT, 'admin-sidebar.png'), fullPage: true });

  const navTab = (idx) => page.locator('aside nav').first().locator('button').nth(idx);

  const clickTab = async (idx) => {
    await navTab(idx).click({ timeout: 15000 });
    await delay(900);
  };

  await clickTab(1);
  await page.screenshot({ path: path.join(OUT, 'admin-setup.png') });

  await clickTab(2);
  await page.screenshot({ path: path.join(OUT, 'admin-live-monitor.png') });

  await clickTab(3);
  await page.screenshot({ path: path.join(OUT, 'admin-pipeline.png') });

  await clickTab(4);
  await page.screenshot({ path: path.join(OUT, 'admin-new-product.png') });

  await clickTab(5);
  await page.screenshot({ path: path.join(OUT, 'admin-workshop.png') });

  await clickTab(8);
  await page.screenshot({ path: path.join(OUT, 'admin-providers.png') });

  await clickTab(9);
  await page.screenshot({ path: path.join(OUT, 'admin-llm-logs.png') });

  await clickTab(14);
  await page.screenshot({ path: path.join(OUT, 'admin-discovery.png') });

  await clickTab(15);
  await page.screenshot({ path: path.join(OUT, 'admin-settings.png') });

  await clickTab(16);
  await page.screenshot({ path: path.join(OUT, 'admin-corporate-chat.png') });

  await clickTab(17);
  await page.screenshot({ path: path.join(OUT, 'admin-brainstorming.png') });

  await browser.close();

  const PUBLIC_OUT = path.join(REPO_ROOT, 'web/frontend/public/docs-screenshots');
  fs.mkdirSync(PUBLIC_OUT, { recursive: true });
  for (const name of fs.readdirSync(OUT)) {
    if (!name.endsWith('.png')) continue;
    fs.copyFileSync(path.join(OUT, name), path.join(PUBLIC_OUT, name));
  }
  console.log('OK — screenshots saved to', OUT);
  console.log('    copied PNGs to', PUBLIC_OUT, '(for /docs in-app)');
}

main().catch((e) => {
  console.error('capture-docs-screenshots failed:', e.message || e);
  process.exit(1);
});
