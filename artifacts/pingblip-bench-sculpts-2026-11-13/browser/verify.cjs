const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { writeFile } = require('node:fs/promises');
const path = require('node:path');

const { chromium, devices } = require(path.join(process.cwd(), 'node_modules/playwright'));
const sharp = require(path.join(process.cwd(), 'pingblip/memeforge/node_modules/sharp'));
const [phase, expectedHash, ...requestedViewports] = process.argv.slice(2);
assert.ok(phase && /^[a-z-]+$/.test(phase) && /^[a-f\d]{64}$/.test(expectedHash));
assert.ok(requestedViewports.every(viewport => ['desktop', 'mobile'].includes(viewport)));
const expectedVersion = expectedHash.slice(0, 10);
const modelPath = '/models/glaze-donut.glb';
const benchUrl = 'https://pingblip.com/bench?lang=en';
const report = { phase, startedAt: new Date().toISOString(), expectedHash, benchUrl, renders: [] };
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const pet = {
  id: 'donut-visual-qa', speciesId: 'glaze-donut', stage: 'awake', evolved: true,
  feedCount: 5, hungry: false, asleep: false, feedReady: false,
  nextFeedAt: new Date(Date.now() + 4 * 3600000).toISOString(),
  hatchProofId: 'qa-proof', source: 'catch',
  species: {
    id: 'glaze-donut', name: 'Glaze Donut', type: 'snack', typeLabel: 'Snack',
    diet: { label: 'Dawn weather' }, sceneId: 'candy-dump', rarity: 'common', packId: 'snack-cult',
  },
};

async function mockPlayerApi(route, url) {
  if (route.request().method() !== 'GET') {
    return route.fulfill({ json: { ok: true } });
  }
  if (url.pathname === '/api/bench') {
    return route.fulfill({ json: {
      creatures: [pet], activeCreatureId: pet.id, seen: 1, creditsMilli: 190,
      refCode: 'qa', goal: null, closedPacks: [], holds: [], onboardingDone: true, packs: [],
    } });
  }
  if (url.pathname === '/api/credits') {
    return route.fulfill({ json: {
      creditsMilli: 190, houseClaimedToday: true,
      economy: { houseGrantMilli: 250, costs: { feed: 30 } },
    } });
  }
  if (url.pathname === '/api/session') {
    return route.fulfill({ json: { user: {
      id: 'donut-visual-qa', name: 'Visual QA', refCode: 'qa', guest: true, owned: [],
    } } });
  }
  return route.fulfill({ json: { ok: true } });
}

async function modelMetadata(response) {
  const bytes = await response.body();
  const jsonLength = bytes.readUInt32LE(12);
  const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8'));
  return {
    url: response.url(), status: response.status(), sha256: hash(bytes), bytes: bytes.length,
    icingNodes: gltf.nodes.map(node => node.name).filter(name => /glaze|drip/i.test(name ?? '')),
  };
}

async function verifyViewport(browser, viewportName, viewportOptions) {
  const context = await browser.newContext({ ...viewportOptions, serviceWorkers: 'block', locale: 'en-US' });
  const page = await context.newPage();
  const entry = { viewport: viewportName, pageErrors: [], consoleErrors: [], models: [] };
  const models = [];
  report.renders.push(entry);
  await context.route('**/*', route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) return mockPlayerApi(route, url);
    if (!['GET', 'HEAD'].includes(request.method())) return route.abort();
    return route.continue();
  });
  page.on('response', response => {
    if (new URL(response.url()).pathname === modelPath) models.push(modelMetadata(response));
  });
  page.on('pageerror', error => entry.pageErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') entry.consoleErrors.push(message.text());
  });

  try {
    const modelResponse = page.waitForResponse(response => new URL(response.url()).pathname === modelPath, { timeout: 65000 });
    modelResponse.catch(() => {});
    const documentResponse = await page.goto(benchUrl, { waitUntil: 'domcontentloaded', timeout: 50000 });
    assert.equal(documentResponse?.status(), 200);
    const heading = page.getByRole('heading', { name: /^glaze\s*donut$/i });
    await heading.waitFor({ timeout: 20000 });
    await page.getByText(/^snack · common · catch · awake · evolved$/i).waitFor({ timeout: 20000 });
    await modelResponse;
    entry.models = await Promise.all(models);
    const canvas = page.locator('canvas[aria-label="Drag to turn the figurine"]');
    await canvas.waitFor({ timeout: 20000 });
    await page.waitForTimeout(3700);

    const box = await canvas.boundingBox();
    assert.ok(box && box.width > 200 && box.height > 200, 'Canvas has no room to draw');
    entry.canvas = box;
    const screenshot = await canvas.screenshot();
    const { data, info } = await sharp(screenshot).removeAlpha().raw().toBuffer({ resolveWithObject: true });
    let pinkPixels = 0;
    for (let offset = 0; offset < data.length; offset += info.channels) {
      const red = data[offset], green = data[offset + 1], blue = data[offset + 2];
      if (red > 150 && blue > 100 && green > 85 && blue > green * 1.04 && red > blue * 1.03) {
        pinkPixels += 1;
      }
    }
    entry.pinkPixelFraction = pinkPixels / (info.width * info.height);
    entry.canvasScreenshot = `${phase}-${viewportName}-canvas.png`;
    await writeFile(path.join(__dirname, entry.canvasScreenshot), screenshot);
    entry.benchScreenshot = `${phase}-${viewportName}-bench.png`;
    await page.screenshot({ path: path.join(__dirname, entry.benchScreenshot) });
    // Bloom and animated yaw change the amount of saturated pink. This is only
    // a minimum draw check. Use the captured frames to review the silhouette.
    assert.ok(entry.pinkPixelFraction > 0.008, 'Canvas has almost no pink pixels');
    assert.ok(entry.models.length > 0);
    for (const model of entry.models) {
      assert.equal(model.status, 200);
      assert.equal(new URL(model.url).searchParams.get('v'), expectedVersion);
      assert.equal(model.sha256, expectedHash);
    }
    assert.deepEqual(entry.pageErrors, []);
    console.log(viewportName, JSON.stringify(entry.models));
  } finally {
    await context.close();
  }
}

async function main() {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
  });
  try {
    if (!requestedViewports.length || requestedViewports.includes('desktop')) {
      await verifyViewport(browser, 'desktop', { viewport: { width: 1460, height: 1040 }, deviceScaleFactor: 1 });
    }
    if (!requestedViewports.length || requestedViewports.includes('mobile')) {
      await verifyViewport(browser, 'mobile', devices['iPhone 13']);
    }
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
  await writeFile(path.join(__dirname, phase + '.json'), JSON.stringify(report, null, 2) + '\n');
});
