#!/usr/bin/env node
/**
 * Captures Admin + public UI screenshots into ../../docs/assets/screenshots/
 *
 * Usage (from web/frontend):
 *   npx playwright install chromium
 *   npm run capture-docs-screenshots
 *
 * Env:
 *   DOCS_SCREENSHOT_BASE_URL — default http://203.0.113.10:9080 (live demo)
 *   ADMIN_PASSWORD — only if password login is required
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  adminLogin,
  captureAdminTab,
  captureDashboardAndSidebar,
  delay,
  waitForMainSettled,
  waitForPipelineReady,
} from './capture-screenshot-helpers.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../../..');
const OUT = path.join(REPO_ROOT, 'docs/assets/screenshots');
const PUBLIC_OUT = path.join(REPO_ROOT, 'web/frontend/public/docs-screenshots');

const BASE = process.env.DOCS_SCREENSHOT_BASE_URL || 'http://203.0.113.10:9080';
const PASSWORD = process.env.ADMIN_PASSWORD || '';

async function main() {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem('admin_locale', 'en');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(180000);

  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await delay(1200);
  await page.screenshot({ path: path.join(OUT, 'public-home.png'), timeout: 120000 });

  await page.goto(`${BASE}/docs`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await delay(1200);
  await page.screenshot({ path: path.join(OUT, 'public-docs.png'), timeout: 120000 });

  await adminLogin(page, { base: BASE, password: PASSWORD, outDir: OUT });
  await captureDashboardAndSidebar(page, OUT);

  const shots = [
    ['setup', 'admin-setup.png', async (p) => {
      await p.getByRole('heading', { name: /Setup wizard|Мастер настройки/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p);
    }],
    ['monitor', 'admin-live-monitor.png', async (p) => {
      await p.getByText(/Live Monitor/i).first().waitFor({ timeout: 90000 });
      await waitForMainSettled(p, { timeout: 120000 });
      await p.evaluate(() => window.scrollTo(0, 420));
      await delay(1000);
    }],
    ['pipeline', 'admin-pipeline.png', async (p) => {
      await waitForPipelineReady(p, { timeout: 300000 });
    }],
    ['new-product', 'admin-new-product.png', async (p) => {
      await p.getByRole('heading', { name: /Create New Product/i }).waitFor({ timeout: 90000 });
      await delay(800);
    }],
    ['workshop', 'admin-workshop.png', async (p) => {
      await p.getByRole('heading', { name: /Product Workshop|Мастерская продуктов/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p);
    }],
    ['providers', 'admin-providers.png', async (p) => {
      await p.getByRole('heading', { name: /LLM Providers|Провайдеры LLM/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p);
    await p.getByRole('heading', { name: /^LLM Providers$/i }).scrollIntoViewIfNeeded();
    await p.evaluate(() => {
      const heading = [...document.querySelectorAll('h2')].find((el) =>
        /LLM Providers|Провайдеры LLM/i.test(el.textContent || ''),
      );
      heading?.scrollIntoView({ block: 'start', behavior: 'instant' });
    });
    await delay(800);
    }],
    ['llm-logs', 'admin-llm-logs.png', async (p) => {
      await p.getByRole('heading', { name: /LLM Call Logs/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p, { timeout: 180000 });
    }],
    ['discovery', 'admin-discovery.png', async (p) => {
      await p.getByRole('heading', { name: /Ranked ideas from signals|Рейтинг идей/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p);
    }],
    ['settings', 'admin-settings.png', async (p) => {
      await p.getByRole('heading', { name: /^Settings$|^Настройки$|^Ajustes$/i }).waitFor({
        timeout: 90000,
      });
      await waitForMainSettled(p, { timeout: 120000 });
    }],
    ['chat', 'admin-corporate-chat.png', async (p) => {
      await p.getByRole('heading', { name: /Corporate Chat|Корпоративный чат/i }).waitFor({ timeout: 90000 });
      await waitForMainSettled(p);
    }],
    ['brainstorming', 'admin-brainstorming.png', async (p) => {
      await p.getByRole('heading', { name: /Brainstorming & Discussions|Мозговые штурмы/i }).waitFor({
        timeout: 90000,
      });
      await waitForMainSettled(p);
    }],
  ];

  for (const [tabId, file, waitFn] of shots) {
    console.log('capture', file, '…');
    await captureAdminTab(page, BASE, tabId, path.join(OUT, file), waitFn);
  }

  await browser.close();

  fs.mkdirSync(PUBLIC_OUT, { recursive: true });
  for (const name of fs.readdirSync(OUT)) {
    if (!name.endsWith('.png')) continue;
    fs.copyFileSync(path.join(OUT, name), path.join(PUBLIC_OUT, name));
  }
  console.log('OK — screenshots saved to', OUT);
  console.log('    copied PNGs to', PUBLIC_OUT);
}

main().catch((e) => {
  console.error('capture-docs-screenshots failed:', e.message || e);
  process.exit(1);
});
