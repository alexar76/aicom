/**
 * Record a Studio walkthrough video on prod: Example → params → Run → swap block → Run.
 * Output: hephaestus/studio/demo-videos/studio-flow.mp4 (+ studio-flow-results.json)
 */
import { chromium } from 'playwright';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const ROOT = path.resolve(import.meta.dirname, '..');
const OUT_DIR = path.join(ROOT, 'hephaestus/studio/demo-videos');
const STUDIO = 'https://modelmarket.dev/studio/?lang=ru';

const results = { runs: [], errors: [] };

async function isNarrow(page) {
  return page.evaluate(() => document.querySelector('.app.narrow') !== null);
}

async function openStatus(page) {
  if (await isNarrow(page)) {
    await page.getByRole('button', { name: 'Статус' }).click();
    await page.waitForTimeout(500);
  }
}

async function openCanvas(page) {
  if (await isNarrow(page)) {
    await page.getByRole('button', { name: 'Полотно' }).click();
    await page.waitForTimeout(500);
  }
}

async function openCatalogue(page) {
  if (await isNarrow(page)) {
    await page.getByRole('button', { name: 'Каталог' }).click();
    await page.waitForTimeout(500);
  }
}

async function waitRunDone(page) {
  await page.waitForFunction(
    () => {
      const btn = [...document.querySelectorAll('header .actions button')].find((b) =>
        /^Запуск/.test(b.textContent?.trim() ?? ''),
      );
      return btn && !btn.disabled && !btn.textContent?.includes('…');
    },
    { timeout: 120000 },
  );
}

async function captureRunSummary(page, label) {
  await openStatus(page);
  await page.waitForTimeout(1000);
  const traceLink = page.locator('.body.trace a[href*="trace"]');
  const traceUrl = (await traceLink.count()) ? await traceLink.getAttribute('href') : null;
  const traceId = (await page.locator('.body.trace .tid').count())
    ? await page.locator('.body.trace .tid').innerText()
    : null;
  const steps = await page.locator('.body.trace ul li').allTextContents();
  const entry = { label, traceId, traceUrl, steps };
  results.runs.push(entry);
  console.log(`[${label}]`, traceId ?? 'no trace', steps.join(' | '));
}

async function selectFlowNode(page, id) {
  await openCanvas(page);
  await page.getByRole('button', { name: 'Fit View' }).click();
  await page.waitForTimeout(700);
  await page.evaluate((nodeId) => {
    const wrap = document.querySelector(`.react-flow__node[data-id="${nodeId}"]`);
    const inner = wrap?.querySelector('.node');
    if (inner instanceof HTMLElement) inner.click();
    else if (wrap instanceof HTMLElement) wrap.click();
  }, id);
  await page.waitForTimeout(900);
  await openStatus(page);
}

async function addFromCatalogue(page, query) {
  await openCatalogue(page);
  const expertBtn = page.getByRole('button', { name: /Весь каталог|опытных/i });
  if (await expertBtn.count()) {
    await expertBtn.click();
    await page.waitForTimeout(700);
  }
  const search = page.locator('.pane.left .search');
  await search.fill(query);
  await page.waitForTimeout(600);
  const cap = page.locator('.pane.left .cap').filter({ hasText: query }).first();
  await cap.click();
  await page.waitForTimeout(1200);
}

await mkdir(OUT_DIR, { recursive: true });

const browser = await chromium.launch({ headless: true, slowMo: 550 });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: OUT_DIR, size: { width: 1440, height: 900 } },
  locale: 'ru-RU',
});
const page = await context.newPage();

try {
  console.log('Opening', STUDIO);
  await page.goto(STUDIO, { waitUntil: 'networkidle', timeout: 90000 });

  const exampleBtn = page.locator('header .actions button').filter({ hasText: /^Пример$/ });
  await exampleBtn.waitFor({ state: 'visible', timeout: 90000 });
  await page.waitForFunction(
    () => {
      const buttons = [...document.querySelectorAll('header .actions button')];
      const ex = buttons.find((b) => b.textContent?.trim() === 'Пример');
      return ex && !ex.disabled;
    },
    { timeout: 90000 },
  );

  // Run 1: example chain (weather → verify), custom device_id
  await exampleBtn.click();
  await page.waitForFunction(
    () => {
      const n = document.querySelector('.react-flow__node[data-id="read"]');
      const canvas = document.querySelector('.canvas');
      return n && !canvas?.hidden && n.getBoundingClientRect().width > 0;
    },
    { timeout: 45000 },
  );
  await page.waitForTimeout(1000);

  await selectFlowNode(page, 'read');
  const deviceField = page.locator('#f-device_id');
  await deviceField.waitFor({ state: 'visible', timeout: 15000 });
  await deviceField.fill('om-wx-01');
  await page.waitForTimeout(1200);

  await page.locator('header .actions button').filter({ hasText: /^Запуск/ }).click();
  await waitRunDone(page);
  await captureRunSummary(page, 'run1_weather_verify');
  await page.waitForTimeout(2500);

  // Swap block: clear verify chain, add platon.random from catalogue
  await page.locator('header .actions button').filter({ hasText: /^Очистить/ }).click();
  await page.waitForTimeout(1200);
  await addFromCatalogue(page, 'platon.random');
  await openCanvas(page);
  await page.evaluate(() => {
    const node = [...document.querySelectorAll('.react-flow__node')].find((n) =>
      /platon\.random/i.test(n.textContent ?? ''),
    );
    const inner = node?.querySelector('.node');
    if (inner instanceof HTMLElement) inner.click();
  });
  await page.waitForTimeout(900);
  await openStatus(page);
  const numBytes = page.locator('#f-num_bytes');
  if (await numBytes.count() > 0) {
    await numBytes.fill('16');
    await page.waitForTimeout(1000);
  }

  // Run 2: new block
  await page.locator('header .actions button').filter({ hasText: /^Запуск/ }).click();
  await waitRunDone(page);
  await captureRunSummary(page, 'run2_platon_random');
  await page.waitForTimeout(3500);
} catch (err) {
  results.errors.push(String(err));
  console.error(err);
} finally {
  await context.close();
  await browser.close();
}

const videos = (await readdir(OUT_DIR)).filter((f) => f.endsWith('.webm'));
const webmPath = videos.length ? path.join(OUT_DIR, videos.sort().at(-1)) : null;
const mp4Path = path.join(OUT_DIR, 'studio-flow.mp4');

if (webmPath) {
  await execFileAsync('ffmpeg', [
    '-y',
    '-i',
    webmPath,
    '-c:v',
    'libx264',
    '-pix_fmt',
    'yuv420p',
    '-movflags',
    '+faststart',
    mp4Path,
  ]);
  console.log('Video:', mp4Path);
}

await writeFile(
  path.join(OUT_DIR, 'studio-flow-results.json'),
  JSON.stringify(results, null, 2),
);
console.log('Results:', path.join(OUT_DIR, 'studio-flow-results.json'));
