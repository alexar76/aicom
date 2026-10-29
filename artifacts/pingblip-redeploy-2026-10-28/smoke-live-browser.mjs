// Read-only browser evidence for the three deployed PingBlip applications.
// Without --live this only writes a local plan. Browser requests that could write
// (guest creation, game sessions and telemetry included) are fulfilled locally;
// this verifies rendering and public assets, not account or feeding flows.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../..');
const FORGE = path.join(REPO, 'pingblip/memeforge');
const require = createRequire(path.join(FORGE, 'package.json'));
const { chromium } = require('playwright');
const sharp = require('sharp');
const args = process.argv.slice(2);
const option = (flag, fallback) => args.includes(flag) ? args[args.indexOf(flag) + 1] : fallback;
const live = args.includes('--live');
const only = option('--only', 'all');
if (!['all', 'forge', 'world', 'share', 'game'].includes(only)) throw new Error('--only must be all, forge, world, share, or game');
const prefix = option('--output-prefix', only === 'all' ? 'browser-smoke' : 'browser-smoke-' + only);
if (!/^[a-z0-9_-]+$/i.test(prefix)) throw new Error('Invalid --output-prefix');
const defaults = ['spark-moth', 'rust-crown', 'winged-bolt', 'cola-cube', 'caramel-bust', 'graveyard-shift', 'taxi-larva'];
const requested = option('--models', defaults.join(',')).split(',');
const source = await readFile(path.join(FORGE, 'src/data/mascots.ts'), 'utf8');
const roster = [...source.matchAll(/\{ id: "([^"]+)", packId: "([^"]+)", name: "([^"]+)"/g)].map(([, id, packId, name]) => ({ id, packId, name }));
const models = requested.map(id => {
 const row = roster.find(row => row.id === id);
 if (!row) throw new Error('Unknown model: ' + id);
 return row;
});
const versions = JSON.parse(await readFile(path.join(FORGE, 'src/data/model-versions.json'), 'utf8'));
const sha256 = body => createHash('sha256').update(body).digest('hex');
const expected = {};
for (const model of models) {
 const glb = await readFile(path.join(FORGE, 'public/models', model.id + '.glb'));
 const preview = await readFile(path.join(FORGE, 'public/dex', model.id + '.webp'));
 expected[model.id] = { modelSha256: sha256(glb), modelVersion: versions[model.id], previewSha256: sha256(preview) };
 if (expected[model.id].modelSha256.slice(0, 10) !== versions[model.id]) throw new Error('Local version mismatch: ' + model.id);
}
const origins = { forge: 'https://forge.pingblip.com', game: 'https://pingblip.com', world: 'https://world.pingblip.com' };
const packs = [...new Set(models.map(model => model.packId))];
const plan = {
 generatedAt: new Date().toISOString(), liveRequested: live, only, models, expected,
 forgeRoutes: models.map(model => `${origins.forge}/forge?pack=${model.packId}&mascot=${model.id}&cutout=1`),
 worldShelfRoutes: models.map(model => `${origins.world}/shelf/${model.id}`),
 worldPackRoutes: packs.map(pack => `${origins.world}/packs/${pack}`),
 gameShareRoutes: models.map(model => `${origins.game}/s/${model.id}`),
 gameModelRoutes: models.map(model => `${origins.game}/?from=${model.id}`),
 readOnlyPolicy: 'Fresh browser contexts, no stored accounts, service workers disabled. Every non-GET/HEAD/OPTIONS request is fulfilled locally with 204 and never reaches a server. Share SSR previews are inspected with JavaScript disabled because their normal client behavior immediately redirects home.',
};
if (!live) {
 await writeFile(path.join(HERE, prefix + '-plan.json'), JSON.stringify(plan, null, 2) + '\n');
 console.log('Prepared local browser plan for ' + models.length + ' models and ' + packs.length + ' packs; no live requests. Add --live after deployment.');
 process.exit(0);
}

const shotDir = path.join(HERE, prefix);
await mkdir(shotDir, { recursive: true });
const report = { ...plan, startedAt: new Date().toISOString(), checks: [], failures: [], suppressedWrites: [], compiledGameVersions: null };
const scripts = new Map();
const scriptLoads = [];
const contexts = [];
const browser = await chromium.launch({
 headless: true,
 executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
 args: ['--enable-webgl', '--ignore-gpu-blocklist', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding'],
});

function assert(condition, message) { if (!condition) throw new Error(message); }
function normalized(text) { return text.toLowerCase().replace(/[^a-z0-9]/g, ''); }
async function context(options = {}) {
 const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 1, locale: 'en-US', serviceWorkers: 'block', ...options });
 contexts.push(ctx);
 await ctx.route('**/*', async route => {
  const req = route.request();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method())) {
   const url = new URL(req.url());
   const knownAutomaticWrite = ['/api/auth/guest', '/api/session', '/api/events'].includes(url.pathname);
   report.suppressedWrites.push({ method: req.method(), origin: url.origin, path: url.pathname, knownAutomaticWrite });
   // No POST body or response cookie is recorded, and no remote mutation occurs.
   await route.fulfill({ status: 204, body: '', headers: { 'x-pingblip-verification': 'read-only-write-suppressed' } });
   return;
  }
  await route.continue();
 });
 return ctx;
}
function attachJournal(page, item, captureGameScripts = false) {
 const consoleHandler = message => {
  if (message.type() === 'error') item.consoleErrors.push({ text: message.text(), location: message.location() });
 };
 const errorHandler = error => item.pageErrors.push(String(error));
 const failedHandler = request => item.failedRequests.push({ url: request.url(), error: request.failure()?.errorText });
 const responseHandler = response => {
  const url = response.url();
  if (response.status() >= 400) item.httpErrors.push({ url, status: response.status(), type: response.request().resourceType() });
  if (captureGameScripts && response.status() === 200 && url.startsWith(origins.game + '/_next/static/') && /\.js(?:\?|$)/.test(url) && !scripts.has(url)) {
   scripts.set(url, null);
   scriptLoads.push(response.text().then(body => scripts.set(url, body)).catch(error => scripts.set(url, { error: String(error) })));
  }
 };
 page.on('console', consoleHandler); page.on('pageerror', errorHandler); page.on('requestfailed', failedHandler); page.on('response', responseHandler);
 return () => { page.off('console', consoleHandler); page.off('pageerror', errorHandler); page.off('requestfailed', failedHandler); page.off('response', responseHandler); };
}
async function check(label, page, action, captureGameScripts = false) {
 const item = { label, startedAt: new Date().toISOString(), consoleErrors: [], pageErrors: [], failedRequests: [], httpErrors: [] };
 const detach = attachJournal(page, item, captureGameScripts);
 try {
  await action(item);
  await page.waitForTimeout(150);
  assert(!item.pageErrors.length, 'Uncaught browser errors: ' + item.pageErrors.join('; '));
  assert(!item.consoleErrors.length, 'Console errors: ' + item.consoleErrors.map(error => error.text).join('; '));
  const essentialHttpErrors = item.httpErrors.filter(error => ['document', 'script', 'stylesheet'].includes(error.type) || /\/(models|dex)\//.test(error.url));
  assert(!essentialHttpErrors.length, 'Public page/assets failed: ' + JSON.stringify(essentialHttpErrors));
  item.ok = true;
  console.log('PASS ' + label);
 } catch (error) {
  item.ok = false; item.error = String(error); report.failures.push({ label, error: String(error) });
  await page.screenshot({ path: path.join(shotDir, label.replace(/[^a-z0-9_-]/gi, '-') + '-failure.png') }).catch(() => {});
  console.log('FAIL ' + label + ': ' + error);
 } finally {
  item.finalUrl = page.url(); item.completedAt = new Date().toISOString(); detach(); report.checks.push(item);
 }
}
async function load(page, url) {
 const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 });
 assert(response?.status() === 200, 'Document status ' + response?.status() + ' at ' + url);
 return response;
}
async function preview(page, model, item, documentUrl, checkLinks = true) {
 const delivered = page.waitForResponse(response => new URL(response.url()).pathname === `/dex/${model.id}.webp`, { timeout: 35_000 }).catch(() => null);
 if (documentUrl) await load(page, documentUrl);
 const image = page.locator(`img[src="/dex/${model.id}.webp"]`).first();
 await image.scrollIntoViewIfNeeded({ timeout: 20_000 });
 await page.waitForFunction(id => {
  const image = document.querySelector(`img[src="/dex/${id}.webp"]`);
  return image?.complete && image.naturalWidth > 0 && image.naturalHeight > 0;
 }, model.id, { timeout: 35_000 });
 const response = await delivered;
 assert(response?.status() === 200, 'Preview response missing or not 200: ' + model.id);
 const body = await response.body();
 const actualHash = sha256(body);
 assert(actualHash === expected[model.id].previewSha256, 'Browser preview bytes differ: ' + model.id);
 const dimensions = await image.evaluate(image => ({ naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight, src: image.currentSrc }));
 item.previews ??= []; item.previews.push({ id: model.id, url: response.url(), status: response.status(), sha256: actualHash, ...dimensions });
 if (checkLinks) await originLinks(page, item, [origins.game, origins.forge]);
}
async function originLinks(page, item, required) {
 const links = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map(a => a.href).filter(href => /^https?:/.test(href)));
 assert(!links.some(link => /https?:\/\/(?:localhost|127\.0\.0\.1)(?::|\/|$)/.test(link)), 'A link points to localhost');
 for (const origin of required) assert(links.some(link => new URL(link).origin === origin), 'Missing public origin link: ' + origin);
 item.linkOrigins = [...new Set(links.map(link => new URL(link).origin))];
}
async function canvasFrame(page, capture = false) {
 return page.evaluate(capture => {
  const canvas = document.querySelector('canvas');
  if (!canvas) return null;
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl || gl.isContextLost()) return { contextLost: true };
  // A small center-only window can land entirely on a flat belly or the gap
  // between wings. Probe across the whole drawing buffer so a correctly drawn
  // model cannot be classified as blank merely because its center is uniform.
  const w = canvas.width;
  const h = canvas.height;
  const pixels = new Uint8ClampedArray(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
  let ink = 0, lit = 0, samples = 0, sum = 0, sumSq = 0; const colors = new Set();
  for (let i = 0; i < pixels.length; i += 4 * (capture ? 31 : Math.max(7, Math.floor(w * h / 10000)))) {
   const [r, g, b, a] = pixels.subarray(i, i + 4); const intensity = (r + g + b) / 3;
   samples++; if (a > 8) ink++; if (r + g + b > 40 && a > 8) lit++;
   sum += intensity; sumSq += intensity * intensity; colors.add((r >> 4) * 256 + (g >> 4) * 16 + (b >> 4));
  }
  const result = { width: canvas.width, height: canvas.height, inkPct: ink / samples, litPct: lit / samples, intensityStdDev: Math.sqrt(Math.max(0, sumSq / samples - (sum / samples) ** 2)), quantizedColors: colors.size, contextLost: false };
  if (capture) {
   const raw = document.createElement('canvas'); raw.width = w; raw.height = h; raw.getContext('2d').putImageData(new ImageData(pixels, w, h), 0, 0);
   const flipped = document.createElement('canvas'); flipped.width = w; flipped.height = h;
   const context = flipped.getContext('2d'); context.translate(0, h); context.scale(1, -1); context.drawImage(raw, 0, 0);
   result.png = flipped.toDataURL('image/png');
  }
  return result;
 }, capture);
}
async function renderedModel(page, model, item, url, site) {
 const delivered = page.waitForResponse(response => new URL(response.url()).pathname === `/models/${model.id}.glb`, { timeout: 45_000 }).catch(() => null);
 await load(page, url);
 await page.waitForFunction(() => {
  const canvas = document.querySelector('canvas'); return canvas && canvas.width > 64 && canvas.height > 64;
 }, undefined, { timeout: 45_000, polling: 400 });
 const response = await delivered;
 assert(response?.status() === 200, 'Model response missing/not 200: ' + model.id);
 const requestUrl = new URL(response.url());
 const version = requestUrl.searchParams.get('v');
 assert(version === expected[model.id].modelVersion, 'Compiled model URL has stale version: ' + model.id + ' got ' + version + ' expected ' + expected[model.id].modelVersion);
 assert(requestUrl.origin === origins[site], 'Unexpected model origin: ' + requestUrl.origin);
 const actualHash = sha256(await response.body());
 assert(actualHash === expected[model.id].modelSha256, 'Browser model bytes differ: ' + model.id);
 item.model = { id: model.id, url: response.url(), status: response.status(), version, sha256: actualHash };
 const attributes = await page.evaluate(() => {
  const canvas = document.querySelector('canvas');
  const gl = canvas?.getContext('webgl2') || canvas?.getContext('webgl');
  return { contextLost: !gl || gl.isContextLost(), preserveDrawingBuffer: gl?.getContextAttributes()?.preserveDrawingBuffer };
 });
 assert(!attributes.contextLost, 'WebGL context lost');
 if (!attributes.preserveDrawingBuffer) {
  // The production game deliberately lets the browser clear its WebGL buffer
  // after compositing to save GPU memory. gl.readPixels outside a render callback
  // therefore sees zeros even when the displayed model is healthy.
  await page.waitForTimeout(1800);
  const png = await page.locator('canvas').first().screenshot();
  const { data, info } = await sharp(png).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  let sum = 0, sumSq = 0, samples = 0, lit = 0; const colors = new Set();
  for (let i = 0; i < data.length; i += 4 * Math.max(7, Math.floor(info.width * info.height / 12000))) {
   const r = data[i], g = data[i + 1], b = data[i + 2], value = (r + g + b) / 3;
   samples++; sum += value; sumSq += value * value;
   if (r + g + b > 40) lit++;
   colors.add((r >> 4) * 256 + (g >> 4) * 16 + (b >> 4));
  }
  item.canvas = { captureMethod: 'browser compositor screenshot; drawing buffer intentionally not preserved', width: info.width, height: info.height,
   litPct: lit / samples, intensityStdDev: Math.sqrt(Math.max(0, sumSq / samples - (sum / samples) ** 2)), quantizedColors: colors.size, ...attributes };
  assert(item.canvas.quantizedColors > 8 && item.canvas.intensityStdDev > 3, 'Displayed canvas screenshot is blank or flat');
  await writeFile(path.join(shotDir, site + '-' + model.id + '-canvas.png'), png);
  await page.screenshot({ path: path.join(shotDir, site + '-' + model.id + '-page.png') });
  return;
 }
 let ready = false;
 for (let i = 0; i < 20; i++) {
  await page.waitForTimeout(350);
  const frame = await canvasFrame(page);
  item.canvasReadinessProbe = frame;
  if (i >= 4 && frame && !frame.contextLost && frame.inkPct > .02 && frame.quantizedColors > 8 && frame.intensityStdDev > 3) { ready = true; break; }
 }
 assert(ready, 'WebGL canvas did not draw a varied, nonblank frame');
 const frame = await canvasFrame(page, true);
 assert(!frame.contextLost && frame.inkPct > .02 && frame.quantizedColors > 8, 'Final canvas blank or lost');
 const png = frame.png; delete frame.png; item.canvas = frame;
 await writeFile(path.join(shotDir, site + '-' + model.id + '-canvas.png'), Buffer.from(png.split(',')[1], 'base64'));
 await page.screenshot({ path: path.join(shotDir, site + '-' + model.id + '-page.png') });
}

try {
 if (only === 'all' || only === 'forge') {
  const ctx = await context(), page = await ctx.newPage(); await page.bringToFront();
  for (const model of models) await check('forge-' + model.id, page, item => renderedModel(page, model, item, `${origins.forge}/forge?pack=${model.packId}&mascot=${model.id}&cutout=1`, 'forge'));
  await ctx.close();
 }
 if (only === 'all' || only === 'world') {
  const ctx = await context(), page = await ctx.newPage();
  for (const model of models) await check('world-shelf-' + model.id, page, async item => {
   await preview(page, model, item, `${origins.world}/shelf/${model.id}`);
   const heading = await page.locator('h1').innerText(); assert(normalized(heading).includes(normalized(model.name)), 'Wrong shelf heading: ' + heading);
   await page.screenshot({ path: path.join(shotDir, 'world-shelf-' + model.id + '.png') });
  });
  for (const pack of packs) await check('world-pack-' + pack, page, async item => {
   await load(page, `${origins.world}/packs/${pack}`);
   const members = roster.filter(model => model.packId === pack);
   for (const member of members) {
    const image = page.locator(`img[src="/dex/${member.id}.webp"]`).first();
    await image.scrollIntoViewIfNeeded();
    await page.waitForFunction(id => { const image = document.querySelector(`img[src="/dex/${id}.webp"]`); return image?.complete && image.naturalWidth > 0; }, member.id, { timeout: 25_000 });
   }
   item.loadedPackPreviews = members.map(member => member.id);
   item.modifiedModelsPresent = models.filter(model => model.packId === pack).map(model => model.id);
   await originLinks(page, item, [origins.game, origins.forge]);
   await page.screenshot({ path: path.join(shotDir, 'world-pack-' + pack + '.png'), fullPage: true });
  });
  await ctx.close();
 }
 if (only === 'all' || only === 'share') {
  const ctx = await context({ javaScriptEnabled: false }), page = await ctx.newPage();
  for (const model of models) await check('game-share-' + model.id, page, async item => {
   item.javaScriptDisabledReason = 'ShareLanding normally immediately redirects; this inspects the actual static still/links that crawlers and no-JS users receive.';
   await preview(page, model, item, `${origins.game}/s/${model.id}`, false);
   const hrefs = await page.locator('a[href]').evaluateAll(links => links.map(link => link.href));
   assert(hrefs.some(href => { const url = new URL(href); return url.origin === origins.game && url.pathname === '/' && url.searchParams.get('from') === model.id; }), 'Share origin/model handoff link missing');
   item.handoffLinks = hrefs;
   await page.screenshot({ path: path.join(shotDir, 'game-share-' + model.id + '.png') });
  });
  await ctx.close();
 }
 if (only === 'all' || only === 'game') {
  const ctx = await context(), page = await ctx.newPage(); await page.bringToFront();
  for (const model of models) await check('game-' + model.id, page, item => renderedModel(page, model, item, `${origins.game}/?from=${model.id}`, 'game'), true);
  await Promise.allSettled(scriptLoads);
  const found = new Map(); const chunkEvidence = [];
  for (const [url, body] of scripts) {
   if (typeof body !== 'string') { chunkEvidence.push({ url, error: body?.error ?? 'body unavailable' }); continue; }
   const text = body.replace(/\\"/g, '"').replace(/\\'/g, "'"); const entries = [];
   for (const [id, expectedVersion] of Object.entries(versions)) {
    const pattern = new RegExp(String.raw`["']${id}["']\s*:\s*["']([a-f0-9]{10})["']`, 'g');
    for (const match of text.matchAll(pattern)) {
     if (!found.has(id)) found.set(id, new Set()); found.get(id).add(match[1]);
     entries.push({ id, version: match[1], matches: match[1] === expectedVersion });
    }
   }
   chunkEvidence.push({ url, sha256: sha256(body), bytes: Buffer.byteLength(body), modelVersions: entries });
  }
  const mismatches = [];
  for (const [id, values] of found) for (const value of values) if (versions[id] !== value) mismatches.push({ id, observed: value, expected: versions[id] });
  report.compiledGameVersions = { observedRosterIds: found.size, expectedRosterIds: Object.keys(versions).length, mismatches, status: mismatches.length ? 'mismatch' : found.size === Object.keys(versions).length ? 'all-80-match' : 'partial-or-not-observed; selected runtime request versions checked individually', chunks: chunkEvidence };
  if (mismatches.length) report.failures.push({ label: 'compiled-game-model-versions', error: JSON.stringify(mismatches) });
  await ctx.close();
 }
 const unexpectedWrites = report.suppressedWrites.filter(write => !write.knownAutomaticWrite);
 if (unexpectedWrites.length) report.failures.push({ label: 'unexpected-write-attempts', error: JSON.stringify(unexpectedWrites) });
 report.ok = !report.failures.length;
} catch (error) {
 report.failures.push({ label: 'browser-smoke-run', error: String(error) }); report.ok = false;
} finally {
 await browser.close();
 report.completedAt = new Date().toISOString();
 report.summary = { checked: report.checks.length, passed: report.checks.filter(check => check.ok).length, failed: report.checks.filter(check => !check.ok).length, suppressedRemoteWrites: report.suppressedWrites.length };
 await writeFile(path.join(HERE, prefix + '.json'), JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify({ ok: report.ok, ...report.summary, compiledGameVersions: report.compiledGameVersions?.status, report: path.join(HERE, prefix + '.json') }, null, 2));
process.exitCode = report.ok ? 0 : 1;
