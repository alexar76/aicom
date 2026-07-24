#!/usr/bin/env node
/** Fast per-locale admin tab screenshots — sets admin_locale then captures. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, '../../..');
const OUT = path.join(REPO, 'docs/encyclopedia/assets/screenshots');
const BASE = process.env.DOCS_SCREENSHOT_BASE_URL || 'http://5.129.212.122:9080';

const TABS = [
  ['dashboard', 'admin-dashboard.png'],
  ['pipeline', 'admin-pipeline.png'],
  ['monitor', 'admin-live-monitor.png'],
  ['discovery', 'admin-discovery.png'],
];

async function login(page) {
  await page.goto(`${BASE}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(1200);
  const demo = page.getByRole('button', { name: /demo|демо/i });
  if (await demo.isVisible().catch(() => false)) {
    await demo.click();
    await page.waitForURL(/\/admin/, { timeout: 45000 });
  }
  await page.waitForTimeout(2000);
}

async function captureLocale(browser, locale) {
  const dir = path.join(OUT, locale);
  fs.mkdirSync(dir, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript((l) => {
    localStorage.setItem('admin_locale', l);
    localStorage.setItem('marketing_locale', l);
  }, locale);

  // Public home
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(dir, 'public-home.png') });
  console.log(`  ${locale} public-home ✓`);

  await login(page);
  for (const [tab, file] of TABS) {
    await page.goto(`${BASE}/admin?tab=${tab}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(3500);
    await page.screenshot({ path: path.join(dir, file) });
    console.log(`  ${locale} ${file} ✓`);
  }
  await ctx.close();
}

async function main() {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  for (const loc of ['en', 'ru', 'es']) {
    console.log(`\n=== ${loc} ===`);
    try {
      await captureLocale(browser, loc);
    } catch (e) {
      console.error(`  ${loc} failed: ${e.message}`);
      const enDir = path.join(OUT, 'en');
      const dir = path.join(OUT, loc);
      for (const [, f] of TABS) {
        const src = path.join(enDir, f);
        if (fs.existsSync(src)) fs.copyFileSync(src, path.join(dir, f));
      }
    }
  }
  await browser.close();
  console.log('\nDone.');
}

main();
