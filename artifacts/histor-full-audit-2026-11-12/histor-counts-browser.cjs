const assert = require('node:assert/strict');
const { join } = require('node:path');
const { chromium } = require(join(process.cwd(), 'node_modules/playwright'));

const base = 'http://localhost:39456';
const landing = join(process.cwd(), 'histor/docs/landing');
const cases = [
  ['en', 'current index entries', 'remote endpoints in the official registry', 'targets with a pinned tool set', 'entries'],
  ['ru', 'записей в текущем указателе', 'удалённых эндпоинтов в официальном реестре', 'целей с закреплённым набором инструментов', 'записей'],
  ['es', 'entradas en el índice actual', 'endpoints remotos del registro oficial', 'destinos con un conjunto de herramientas fijado', 'entradas'],
  ['fr', 'entrées dans l’index actuel', 'points de terminaison distants du registre officiel', 'cibles avec un ensemble d’outils épinglé', 'entrées'],
  ['zh', '当前索引条目', '官方注册表中的远程端点', '已固定工具集的目标', '条记录'],
];
const digits = (value) => Number(value.replace(/\D/g, ''));
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--disable-gpu'] });
  try {
    for (const [i, [lang, listedLabel, endpointsLabel, pinnedLabel, entries]] of cases.entries()) {
      const page = await browser.newPage({ viewport: i % 2 ? { width: 390, height: 640 } : { width: 1280, height: 720 }, reducedMotion: 'reduce' });
      page.setDefaultTimeout(10000);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const listed = 9870 + i;
      const endpoints = 5430 + i;
      const pinned = 2340 + i;
      const stats = {
        lastRun: { registryServers: 4321, registryEndpoints: endpoints, attempted: 3456, finishedAt: '2026-11-12T10:58:31Z' },
        targets: { listed, pinned },
        changes: { last7d: 3, last30d: 10 }, log: { treeSize: 22 }, clientReports: { last7d: 0 }, crawl: { running: false },
      };
      await page.route('**/*', async (route) => {
        const url = new URL(route.request().url());
        if (url.origin !== base || route.request().resourceType() === 'image' || url.pathname.includes('/loom')) {
          return route.abort();
        }
        if (url.pathname === '/api/v1/stats') return route.fulfill({ json: stats });
        if (url.pathname === '/api/v1/stats/hosts') return route.fulfill({ json: { hosts: [] } });
        if (url.pathname === '/api/v1/servers') return route.fulfill({ json: {
          total: listed, servers: [
            { id: 'remote', name: 'example/remote', endpoint: 'https://example.com/mcp' },
            { id: 'package', name: 'example/package', endpoint: 'npm:example' },
          ],
        } });
        if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404 });
        const path = url.pathname.startsWith('/assets/') ? join(landing, url.pathname) : join(landing, 'index.html');
        return route.fulfill({ path });
      });
      await page.goto(base + '/?lang=' + lang, { waitUntil: 'commit' });
      await page.waitForFunction(() => document.querySelector('#m-endpoints').textContent !== '—');
      assert.equal(digits(await page.locator('#m-endpoints').textContent()), endpoints);
      assert.equal(digits(await page.locator('#m-pinned').textContent()), pinned);
      await page.goto(base + '/stats?lang=' + lang, { waitUntil: 'commit' });
      await page.locator('#view .fact').first().waitFor();
      assert.equal(await page.locator('html').getAttribute('lang'), lang);
      const fact = async (label) => digits(await page.locator('#view .fact')
        .filter({ has: page.getByText(label, { exact: true }) }).locator('.v').textContent());
      assert.equal(await fact(endpointsLabel), endpoints);
      assert.equal(await fact(listedLabel), listed);
      assert.equal(await fact(pinnedLabel), pinned);
      assert.match(await page.locator('#view .muted').first().textContent(), /2026-11-12 10:58 UTC/);
      await page.goto(base + '/servers?lang=' + lang, { waitUntil: 'commit' });
      await page.locator('#view .row-card').nth(1).waitFor();
      const totalLabel = await page.locator('#view .toolbar .faint').textContent();
      assert(totalLabel.includes(entries), totalLabel);
      assert.equal(digits(totalLabel), listed);
      assert.deepEqual(errors, []);
      console.log(lang + ': homepage, stats, and directory use the right fixture counts');
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
