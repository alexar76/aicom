// Run from the workspace root after the production deployment has completed.
// Public app code, images and models load over HTTPS. Player APIs are mocked.
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFile, writeFile } = require('node:fs/promises');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const { chromium } = require(path.join(root, 'node_modules/playwright'));
const sharp = require(path.join(root, 'pingblip/memeforge/node_modules/sharp'));
const version = 'fbd11eee9e';
const expectedModelHash = 'fbd11eee9e2da8120163bd009e594c0ec9628bd06cfdc8d9377c5c9bdb0f49b2';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const report = { startedAt: new Date().toISOString(), expectedModelHash, assets: [], browsers: [] };

async function verifyAsset(url, localFile) {
  const response = await fetch(url, { signal: AbortSignal.timeout(30000), cache: 'no-store' });
  assert.equal(response.status, 200, url);
  const body = Buffer.from(await response.arrayBuffer());
  const expected = await readFile(path.join(root, localFile));
  assert.equal(hash(body), hash(expected), 'Production asset differs from local file: ' + url);
  const item = { url, localFile, bytes: body.length, sha256: hash(body), status: response.status };
  report.assets.push(item);
  console.log('Verified asset ' + url);
  return item;
}

const pet = {
  id: 'bow-visual-qa', speciesId: 'caramel-bust', stage: 'adult', evolved: false,
  feedCount: 3, hungry: false, asleep: false, feedReady: false,
  nextFeedAt: '2026-12-01T12:00:00Z', hatchProofId: 'qa-proof', source: 'weather',
  species: {
    name: 'Caramel Bust', type: 'sugar', typeLabel: 'Sugar',
    diet: { label: 'Warmth' }, sceneId: 'sugar-forge', rarity: 'common', packId: 'sugar-riot',
  },
};

async function mockPlayerApi(route) {
  const request = route.request();
  const url = new URL(request.url());
  if (url.pathname === '/api/bench') {
    return route.fulfill({ json: {
      creatures: [pet], activeCreatureId: pet.id, seen: 1, creditsMilli: 60,
      refCode: 'qa', goal: null, closedPacks: [], holds: [],
    } });
  }
  if (url.pathname === '/api/credits') {
    return route.fulfill({ json: {
      creditsMilli: 60, houseClaimedToday: false,
      economy: { houseGrantMilli: 10, costs: { feed: 30 } },
    } });
  }
  if (url.pathname === '/api/session' && request.method() === 'GET') {
    return route.fulfill({ json: { user: {
      id: 'bow-visual-qa', name: 'Visual QA', refCode: 'qa', guest: true, owned: [],
    } } });
  }
  return route.fulfill({ json: { ok: true } });
}

async function captureFigurine(browser, config) {
  const context = await browser.newContext({
    viewport: { width: 1310, height: 950 }, deviceScaleFactor: 1,
    serviceWorkers: 'block', reducedMotion: 'reduce', locale: 'en-US',
  });
  const page = await context.newPage();
  const record = { app: config.name, url: config.url, pageErrors: [], consoleErrors: [], requestFailures: [], assetResponses: [] };
  const pendingResponses = [];
  page.on('pageerror', error => record.pageErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') record.consoleErrors.push(message.text());
  });
  page.on('requestfailed', request => record.requestFailures.push({
    url: request.url(), error: request.failure()?.errorText,
  }));
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.pathname !== '/models/caramel-bust.glb') return;
    pendingResponses.push((async () => {
      const body = await response.body();
      record.assetResponses.push({ url: response.url(), status: response.status(), sha256: hash(body) });
    })());
  });
  await context.route('**/api/**', mockPlayerApi);
  try {
    const response = await page.goto(config.url, { timeout: 90000 });
    assert.equal(response.status(), 200);
    const canvas = page.locator('canvas[aria-label="Drag to turn the figurine"]');
    await canvas.waitFor({ timeout: 60000 });
    await page.waitForTimeout(2500);
    await Promise.all(pendingResponses);
    assert.ok(record.assetResponses.length, 'No Caramel Bust asset loaded in ' + config.name);
    for (const asset of record.assetResponses) {
      assert.equal(asset.status, 200);
      assert.equal(new URL(asset.url).searchParams.get('v'), version);
      assert.equal(asset.sha256, expectedModelHash);
    }

    const box = await canvas.boundingBox();
    assert.ok(box && box.width > 300 && box.height > 350, 'Canvas has no room to draw');
    record.canvas = box;
    const x = box.x + box.width * 0.36;
    const y = box.y + box.height / 2;
    const stage = config.stage ? page.locator(config.stage) : canvas.locator('..');
    async function drag(dx, dy) {
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.waitForTimeout(130);
      await page.mouse.move(x + dx, y + dy, { steps: 4 });
      await page.mouse.up();
      await page.waitForTimeout(450);
    }

    await drag(115, 0);
    const image = await canvas.screenshot();
    const { data, info } = await sharp(image).removeAlpha().raw().toBuffer({ resolveWithObject: true });
    let goldPixels = 0;
    for (let offset = 0; offset < data.length; offset += info.channels) {
      const red = data[offset], green = data[offset + 1], blue = data[offset + 2];
      if (red > 95 && green > 55 && green > red * 0.37 && blue < red * 0.8) goldPixels += 1;
    }
    record.goldPixelFraction = goldPixels / (info.width * info.height);
    assert.ok(record.goldPixelFraction > 0.05, 'Caramel figurine did not draw');
    await stage.screenshot({ path: path.join(__dirname, config.name + '-front.png') });
    await drag(-192, -81);
    await stage.screenshot({ path: path.join(__dirname, config.name + '-pitched-profile.png') });
    await page.mouse.dblclick(x, y);
    await page.waitForTimeout(250);
    assert.deepEqual(record.pageErrors, []);
    console.log('Verified browser rendering ' + config.name);
  } finally {
    report.browsers.push(record);
    await context.close();
  }
}

async function captureWorld(browser) {
  const context = await browser.newContext({ viewport: { width: 1310, height: 950 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    const response = await page.goto('https://world.pingblip.com/shelf/caramel-bust?lang=en', { timeout: 90000 });
    assert.equal(response.status(), 200);
    const image = page.locator('.species-hero img.relic-sculpt');
    await image.waitFor();
    await image.evaluate(node => node.decode());
    assert.equal(await image.evaluate(node => node.naturalWidth), 640);
    const ogUrl = await page.locator('meta[property="og:image"]').getAttribute('content');
    assert.equal(ogUrl, 'https://world.pingblip.com/shelf/caramel-bust/opengraph-image?v=' + version);
    assert.equal(await page.locator('meta[name="twitter:image"]').getAttribute('content'), ogUrl);
    const ogResponse = await fetch(ogUrl, { signal: AbortSignal.timeout(30000) });
    assert.equal(ogResponse.status, 200);
    const ogBytes = Buffer.from(await ogResponse.arrayBuffer());
    const metadata = await sharp(ogBytes).metadata();
    assert.equal(metadata.width, 1200);
    assert.equal(metadata.height, 630);
    await writeFile(path.join(__dirname, 'world-og-card.png'), ogBytes);
    await page.locator('.species-hero').screenshot({ path: path.join(__dirname, 'world-shelf.png') });
    assert.deepEqual(errors, []);
    report.world = { url: page.url(), ogUrl, ogBytes: ogBytes.length, ogSha256: hash(ogBytes), pageErrors: errors };
    console.log('Verified World shelf and versioned social card');
  } finally {
    await context.close();
  }
}

async function main() {
  assert.equal(hash(await readFile(path.join(root, 'pingblip/memeforge/public/models/caramel-bust.glb'))), expectedModelHash);
  for (const domain of ['pingblip.com', 'forge.pingblip.com']) {
    await verifyAsset('https://' + domain + '/models/caramel-bust.glb?v=' + version,
      'pingblip/memeforge/public/models/caramel-bust.glb');
  }
  for (const domain of ['pingblip.com', 'forge.pingblip.com', 'world.pingblip.com']) {
    await verifyAsset('https://' + domain + '/dex/caramel-bust.webp',
      'pingblip/world/public/dex/caramel-bust.webp');
  }
  await verifyAsset('https://world.pingblip.com/dex/og/caramel-bust.jpg',
    'pingblip/world/public/dex/og/caramel-bust.jpg');

  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
  });
  try {
    await captureFigurine(browser, { name: 'bench', url: 'https://pingblip.com/bench?lang=en', stage: '.pingblip-stage' });
    await captureFigurine(browser, { name: 'forge', url: 'https://forge.pingblip.com/forge?pack=sugar-riot&mascot=caramel-bust&lang=en' });
    await captureWorld(browser);
  } finally {
    await browser.close();
  }
  report.passed = true;
}

main().catch(error => {
  report.passed = false;
  report.error = String(error.stack || error);
  console.error(report.error);
  process.exitCode = 1;
}).finally(async () => {
  report.finishedAt = new Date().toISOString();
  await writeFile(path.join(__dirname, 'verification.json'), JSON.stringify(report, null, 2) + '\n');
});
