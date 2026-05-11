#!/usr/bin/env node
/**
 * Captures Admin UI screenshots into ../../docs/assets/screenshots/
 * Requires: running app (e.g. http://127.0.0.1:9080), default admin password.
 *
 * Usage (from web/frontend):
 *   npx playwright install chromium
 *   node scripts/capture-docs-screenshots.mjs
 *
 * Env:
 *   DOCS_SCREENSHOT_BASE_URL — default http://127.0.0.1:9080
 *   ADMIN_PASSWORD — default admin123
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

  await page.goto(`${BASE}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await delay(500);
  await page.screenshot({ path: path.join(OUT, 'admin-login.png') });

  const passInput =
    page.getByPlaceholder('Enter admin password').or(page.locator('input[type="password"]'));
  await passInput.fill(PASSWORD);
  await page.getByRole('button', { name: /^Login$/i }).click();
  await page.waitForURL(/\/admin(\?|$)/, { timeout: 45000 });
  await delay(600);

  await page.screenshot({ path: path.join(OUT, 'admin-dashboard.png') });
  await page.screenshot({ path: path.join(OUT, 'admin-sidebar.png'), fullPage: true });

  /** Sidebar starts collapsed on desktop (icons only); buttons have no text labels — use tab order. */
  const navTab = (idx) => page.locator('aside nav').first().locator('button').nth(idx);

  const clickTab = async (idx) => {
    await navTab(idx).click({ timeout: 15000 });
    await delay(900);
  };

  // 0 Dashboard … 2 Pipeline, 6 LLM Providers, 7 LLM Logs, 13 Corporate Chat, 14 Brainstorming
  await clickTab(2);
  await page.screenshot({ path: path.join(OUT, 'admin-pipeline.png') });

  await clickTab(6);
  await page.screenshot({ path: path.join(OUT, 'admin-providers.png') });

  await clickTab(7);
  await page.screenshot({ path: path.join(OUT, 'admin-llm-logs.png') });

  await clickTab(13);
  await page.screenshot({ path: path.join(OUT, 'admin-corporate-chat.png') });

  await clickTab(14);
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
