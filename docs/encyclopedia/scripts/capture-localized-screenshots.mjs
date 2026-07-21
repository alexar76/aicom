#!/usr/bin/env node
/**
 * Capture admin UI screenshots in en / ru / es for the encyclopedia.
 * Waits for real data — not lazy-tab "Loading…" placeholders.
 *
 * Usage: node docs/encyclopedia/scripts/capture-localized-screenshots.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';
import {
  delay,
  isPasswordlessDemo,
  waitForDashboardReady,
  waitForPipelineReady,
  waitForMainSettled,
} from '../../../web/frontend/scripts/capture-screenshot-helpers.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../../..');
const OUT_BASE = path.join(REPO_ROOT, 'docs/encyclopedia/assets/screenshots');
const BASE = process.env.DOCS_SCREENSHOT_BASE_URL || 'http://5.129.212.122:9080';

const LOCALES = ['en', 'ru', 'es'];

const SHOTS = [
  { file: 'public-home.png', url: '/', wait: 3000 },
  { file: 'admin-dashboard.png', tab: 'dashboard', waitFn: waitForDashboardReady },
  { file: 'admin-pipeline.png', tab: 'pipeline', waitFn: waitForPipelineReady },
  {
    file: 'admin-live-monitor.png',
    tab: 'monitor',
    waitFn: waitLiveMonitor,
  },
  {
    file: 'admin-discovery.png',
    tab: 'discovery',
    waitFn: waitDiscovery,
  },
];

async function waitLiveMonitor(page) {
  await page.getByText(/Live Monitor/i).first().waitFor({ timeout: 90000 });
  await waitForMainSettled(page, { timeout: 120000 });

  // Demo replay video often renders as a blank white frame in headless Chrome — hide it for docs.
  await page.evaluate(() => {
    const demoHeading = [...document.querySelectorAll('h3')].find((h) =>
      /Demo replay/i.test(h.textContent || '')
    );
    const card = demoHeading?.closest('div.border');
    if (card instanceof HTMLElement) card.style.display = 'none';
  });

  await page
    .getByText(/Pipeline Completion|Завершение пайплайна|Finalización del pipeline/i)
    .first()
    .waitFor({ timeout: 90000 })
    .catch(() => {});

  const gauge = page
    .getByText(/Pipeline Completion|Agent Activity|Активность агентов|Actividad de agentes/i)
    .first();
  if (await gauge.isVisible().catch(() => false)) {
    await gauge.scrollIntoViewIfNeeded();
  } else {
    await page.evaluate(() => window.scrollTo(0, 720));
  }
  await delay(1500);
}

async function waitDiscovery(page) {
  await page
    .getByRole('heading', { name: /Ranked ideas from signals|Рейтинг идей|Ideas clasificadas/i })
    .first()
    .waitFor({ timeout: 90000 });
  await waitForMainSettled(page);
  await delay(1500);
}

async function preferLocale(page, locale) {
  await page.evaluate((l) => {
    window.localStorage.setItem('admin_locale', l);
    window.localStorage.setItem('marketing_locale', l);
  }, locale);

  const asideSelect = page.locator('aside select').first();
  if (await asideSelect.isVisible().catch(() => false)) {
    const val = await asideSelect.inputValue().catch(() => '');
    if (val !== locale) {
      await asideSelect.selectOption(locale);
      await delay(800);
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 120000 });
      await delay(1500);
    }
    return;
  }

  const langBtn = page.getByRole('button', { name: new RegExp(`^${locale}$`, 'i') }).first();
  if (await langBtn.isVisible().catch(() => false)) {
    await langBtn.click();
    await delay(1200);
    return;
  }

  const loginSelect = page
    .locator('select')
    .filter({ has: page.locator(`option[value="${locale}"]`) })
    .first();
  if (await loginSelect.isVisible().catch(() => false)) {
    const val = await loginSelect.inputValue().catch(() => '');
    if (val !== locale) {
      await loginSelect.selectOption(locale);
      await delay(500);
    }
  }
}

async function loginAdmin(page, locale) {
  const passwordless = await isPasswordlessDemo(BASE);
  await page.goto(`${BASE}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await preferLocale(page, locale);
  await delay(1500);

  const passInput = page
    .getByPlaceholder(/admin password|пароль|contraseña/i)
    .or(page.locator('input[type="password"]'));
  const passVisible = !passwordless && (await passInput.isVisible().catch(() => false));
  if (passVisible) {
    const pass = process.env.ADMIN_PASSWORD;
    if (!pass) throw new Error('Password field visible — set ADMIN_PASSWORD');
    await passInput.fill(pass);
    await page.getByRole('button', { name: /^Login$|^Войти$|^Entrar$/i }).click();
  } else {
    await page
      .getByRole('button', {
        name: /Enter admin demo|Открыть демо|Entrar al demo|demo/i,
      })
      .click();
  }
  await page.waitForURL(/\/admin/, { timeout: 90000 });
  await preferLocale(page, locale);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  await waitForDashboardReady(page);
}

async function openTab(page, tabId, locale) {
  await page.goto(`${BASE}/admin?tab=${tabId}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await preferLocale(page, locale);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  await delay(800);
}

async function assertPipelineScreenshot(page, dest) {
  const body = await page.locator('main').innerText().catch(() => '');
  if (/Loading pipeline/i.test(body) && !/prod-[a-f0-9]{6,}/i.test(body)) {
    throw new Error('Pipeline still loading — no product rows');
  }
  if (!/prod-[a-f0-9]{6,}/i.test(body)) {
    throw new Error('Pipeline screenshot missing product catalog rows');
  }
  const stat = fs.statSync(dest);
  if (stat.size < 80_000) {
    throw new Error(`Pipeline screenshot too small (${stat.size} bytes)`);
  }
}

async function assertDashboardScreenshot(page, dest) {
  const body = await page.locator('main').innerText().catch(() => '');
  if (/Loading metrics|Загрузка метрик/i.test(body)) {
    throw new Error('Dashboard still loading metrics');
  }
  const stat = fs.statSync(dest);
  if (stat.size < 80_000) {
    throw new Error(`Dashboard screenshot too small (${stat.size} bytes)`);
  }
}

async function main() {
  fs.mkdirSync(OUT_BASE, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const failures = [];

  for (const locale of LOCALES) {
    const outDir = path.join(OUT_BASE, locale);
    fs.mkdirSync(outDir, { recursive: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();

    await page.addInitScript((loc) => {
      window.localStorage.setItem('admin_locale', loc);
      window.localStorage.setItem('marketing_locale', loc);
    }, locale);

    console.log(`\n=== Locale: ${locale} ===`);

    for (const shot of SHOTS) {
      const dest = path.join(outDir, shot.file);
      try {
        if (shot.url) {
          await page.goto(`${BASE}${shot.url}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
          await preferLocale(page, locale);
          await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {});
          await delay(shot.wait || 2500);
        } else {
          if (shot.tab === 'dashboard') {
            await loginAdmin(page, locale);
          } else {
            await openTab(page, shot.tab, locale);
          }
          if (shot.waitFn) await shot.waitFn(page);
        }
        await page.evaluate(() => window.scrollTo(0, 0));
        await delay(1000);
        await page.screenshot({ path: dest, fullPage: false, timeout: 120000 });

        if (shot.file === 'admin-pipeline.png') await assertPipelineScreenshot(page, dest);
        if (shot.file === 'admin-dashboard.png') await assertDashboardScreenshot(page, dest);

        const kb = (fs.statSync(dest).size / 1024).toFixed(0);
        console.log(`  ✓ ${shot.file} (${kb} KB)`);
      } catch (e) {
        console.error(`  ✗ ${shot.file}: ${e.message}`);
        failures.push(`${locale}/${shot.file}: ${e.message}`);
        const enSrc = path.join(OUT_BASE, 'en', shot.file);
        if (locale !== 'en' && fs.existsSync(enSrc)) {
          fs.copyFileSync(enSrc, dest);
          console.log(`    → fallback: copied en/${shot.file}`);
        }
      }
    }
    await context.close();
  }

  const shared = [
    ['alien-monitor/docs/screenshots/01-full-ecosystem.png', 'alien-ecosystem.png'],
    ['alien-monitor/docs/screenshots/09-ecosystem-simulation.png', 'alien-simulation.png'],
  ];
  const sharedDir = path.join(OUT_BASE, 'shared');
  fs.mkdirSync(sharedDir, { recursive: true });
  for (const [src, dest] of shared) {
    const full = path.join(REPO_ROOT, src);
    if (fs.existsSync(full)) fs.copyFileSync(full, path.join(sharedDir, dest));
  }

  await browser.close();

  if (failures.length) {
    console.error('\nCapture finished with failures:');
    failures.forEach((f) => console.error(`  - ${f}`));
    process.exit(1);
  }
  console.log('\nDone — all screenshots captured with content.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
