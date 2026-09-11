#!/usr/bin/env node
/** Capture admin-dashboard.png only (waits for live KPI data). */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../../..');
const OUT = path.join(REPO_ROOT, 'docs/assets/screenshots');
const PUBLIC_OUT = path.join(REPO_ROOT, 'web/frontend/public/docs-screenshots');

const BASE = process.env.DOCS_SCREENSHOT_BASE_URL || 'http://203.0.113.10:9080';
const PASSWORD = process.env.ADMIN_PASSWORD || '';
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForDashboardReady(page) {
  await page.getByText(/Factory health score|Total Products|Всего продуктов|Индекс здоровья/).first().waitFor({
    timeout: 90000,
  });
  await page.waitForFunction(
    () => {
      let numericStats = 0;
      for (const node of document.querySelectorAll('.tabular-nums')) {
        const text = (node.textContent || '').trim();
        if (/^\d+$/.test(text)) numericStats += 1;
      }
      const spinners = document.querySelectorAll('main .animate-spin');
      return numericStats >= 3 && spinners.length <= 2;
    },
    { timeout: 180000 },
  );
  await delay(3000);
}

async function preferEnglishLocale(page) {
  const select = page.locator('aside select').first();
  if (await select.isVisible().catch(() => false)) {
    await select.selectOption('en');
    await delay(1200);
  }
}

async function isPasswordlessDemo(base) {
  try {
    const res = await fetch(`${base}/api/public/demo-config`);
    if (!res.ok) return false;
    const body = await res.json();
    return Boolean(body.passwordless_admin);
  } catch {
    return false;
  }
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(PUBLIC_OUT, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  page.setDefaultTimeout(180000);

  const dashboardResponse = page.waitForResponse(
    (r) => r.url().includes('/admin/dashboard') && r.status() === 200,
    { timeout: 180000 },
  );

  await page.goto(`${BASE}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await delay(1500);

  const passwordless = await isPasswordlessDemo(BASE);
  const passInput = page.getByPlaceholder('Enter admin password').or(page.locator('input[type="password"]'));
  if (!passwordless && (await passInput.isVisible().catch(() => false))) {
    if (!PASSWORD) throw new Error('Set ADMIN_PASSWORD');
    await passInput.fill(PASSWORD);
    await page.getByRole('button', { name: /^Login$|^Войти$/i }).click();
  } else {
    await page.getByRole('button', { name: /Enter admin demo|Открыть демо|Entrar al demo/i }).click();
  }

  await page.waitForURL(/\/admin/, { timeout: 60000 });
  await dashboardResponse.catch(() => {});
  await preferEnglishLocale(page);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  try {
    await waitForDashboardReady(page);
  } catch {
    await delay(15000);
  }

  const statsHeading = page.getByText(/^Total Products$|^Всего продуктов$/);
  if (await statsHeading.isVisible().catch(() => false)) {
    await statsHeading.scrollIntoViewIfNeeded();
    await delay(1000);
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  const outPath = path.join(OUT, 'admin-dashboard.png');
  await page.screenshot({ path: outPath, timeout: 120000 });
  fs.copyFileSync(outPath, path.join(PUBLIC_OUT, 'admin-dashboard.png'));

  await browser.close();
  console.log('OK —', outPath);
}

main().catch((e) => {
  console.error(e.message || e);
  process.exit(1);
});
