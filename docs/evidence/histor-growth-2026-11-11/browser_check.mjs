import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const base = 'http://127.0.0.1:9497';
const card = '/s/236eb5f0481cc99c';
const root = process.argv[2];
if (!root) throw new Error('Pass a screenshot output directory.');
await mkdir(root, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const results = [];
async function aboveFold(page, selector) {
  const target = page.locator(selector).first();
  await target.waitFor();
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  assert(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1
    && box.y + box.height <= viewport.height, `Below fold ${selector}: ${JSON.stringify({ box, viewport })}`);
  return Math.round(box.y);
}
try {
  for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 640 }]) {
    const page = await browser.newPage({ viewport, reducedMotion: 'reduce' });
    const exceptions = [];
    page.on('pageerror', e => exceptions.push(String(e)));
    const events = [];
    page.on('response', r => {
      if (r.url().includes('/api/v1/journey/')) events.push([new URL(r.url()).pathname.split('/').at(-1), r.status()]);
    });
    await page.goto(base + card + '?lang=ru&utm_source=qa');
    await page.locator('.desk-entry details summary').waitFor();
    assert.equal(await page.locator('main > :first-child').getAttribute('id'), 'desk');
    const titleY = await aboveFold(page, '.desk-entry h2');
    const changeY = await aboveFold(page, '.desk-entry details summary');
    const atomY = await aboveFold(page, '.desk-entry [data-journey=watch_feed_clicked]');
    const proofY = await aboveFold(page, '.desk-entry a[href$="/proof"]');
    const checkY = await aboveFold(page, '.desk-entry a[href*="/check?sample="]');
    assert.equal(await page.locator('html').getAttribute('lang'), 'ru');
    assert.equal(await page.locator('.desk-entry h2').textContent(), 'AI Applyd');
    await page.screenshot({ path: root + `/card-${viewport.width}.png`, animations: 'disabled' });
    await page.locator('.desk-entry details summary').click();
    assert.equal(await page.locator('.desk-entry details').getAttribute('open'), '');
    assert.match(await page.locator('.desk-entry details').innerText(), /getmattered_/);
    const proofUrl = await page.locator('.desk-entry a[href$="/proof"]').getAttribute('href');
    assert.equal((await page.request.get(base + proofUrl)).status(), 200);
    const feedLink = page.locator('.desk-entry [data-journey=watch_feed_clicked]');
    const feedResponse = await page.request.get(base + (await feedLink.getAttribute('href')));
    assert.match(feedResponse.headers()['content-type'], /application\/atom\+xml/);
    assert.match(await feedResponse.text(), /com\.aiapplyd\/aiapplyd/);
    await page.evaluate(() => document.querySelector('.desk-entry [data-journey=watch_feed_clicked]')
      .addEventListener('click', e => e.preventDefault()));
    const atomEvent = page.waitForResponse(r => r.url().endsWith('/qa/watch_feed_clicked'));
    await feedLink.click();
    assert.equal((await atomEvent).status(), 204);

    await page.goto(base + '/watch?lang=es&utm_source=qa');
    const pilot = page.locator('.desk-entry [data-journey=pilot_contact_clicked]');
    await page.getByText(/29 por 30 días/).waitFor();
    const pilotY = await aboveFold(page, '.desk-entry [data-journey=pilot_contact_clicked]');
    assert.equal(await page.locator('main > :first-child').getAttribute('id'), 'desk');
    assert.equal(await page.locator('.desk-entry h2').textContent(), 'HISTOR Watch para equipos');
    assert.match(await pilot.getAttribute('href'), /^mailto:/);
    await page.screenshot({ path: root + `/watch-${viewport.width}.png`, animations: 'disabled' });
    await page.evaluate(() => document.querySelector('.desk-entry [data-journey=pilot_contact_clicked]')
      .addEventListener('click', e => e.preventDefault()));
    const pilotEvent = page.waitForResponse(r => r.url().endsWith('/qa/pilot_contact_clicked'));
    await pilot.click();
    assert.equal((await pilotEvent).status(), 204);
    const see = page.getByText('Ver un cambio registrado', { exact: true });
    await see.click();
    await page.waitForURL(/\/s\/236eb5f0481cc99c/);
    await page.locator('.desk-entry details summary').waitFor();
    await aboveFold(page, '.desk-entry h2');

    await page.goto(base + '/check?sample=236eb5f0481cc99c&utm_source=qa&lang=en');
    const sample = page.locator('#view .result button.btn-primary').first();
    await sample.waitFor();
    const sampleY = await aboveFold(page, '#view .result button.btn-primary');
    const sampleResult = page.waitForResponse(r => r.url().endsWith('/qa/sample_succeeded'));
    await sample.click();
    await page.getByText(/answer signed by the log key/i).waitFor();
    assert.equal((await sampleResult).status(), 204);
    await page.locator('nav .brand').click();
    assert.equal(await page.locator('main > :first-child').getAttribute('class'), 'hero');
    await page.route('**/api/v1/watch/plan', route => route.fulfill({ status: 503 }));
    const failedPlan = page.waitForResponse(r => r.url().endsWith('/watch/plan'));
    await page.goto(base + '/watch?lang=es&utm_source=qa');
    assert.equal((await failedPlan).status(), 503);
    await aboveFold(page, '.desk-entry [data-journey=pilot_contact_clicked]');
    await aboveFold(page, '.desk-entry a[data-route^="/s/"]');
    assert.deepEqual(exceptions, []);
    results.push({ viewport, titleY, changeY, atomY, proofY, checkY, pilotY, sampleY, events });
    await page.close();
  }
  const staticPage = await browser.newPage({ viewport: { width: 390, height: 640 }, javaScriptEnabled: false });
  await staticPage.goto(base + card + '?lang=ru');
  await aboveFold(staticPage, '.desk-entry h2');
  await aboveFold(staticPage, '.desk-entry [data-journey=watch_feed_clicked]');
  await staticPage.goto(base + '/watch?lang=es');
  await aboveFold(staticPage, '.desk-entry [data-journey=pilot_contact_clicked]');
  await staticPage.close();
  console.log(JSON.stringify({ viewports: results, initialHtmlWithoutScripts: true, planUnavailableKeepsPilot: true }, null, 2));
} finally {
  await browser.close();
}
