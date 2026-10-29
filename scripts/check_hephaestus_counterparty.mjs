/** Offline browser regression: synthetic catalogue/results, no remote or paid calls. */
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = path.resolve(import.meta.dirname, '..');
const dist = path.join(root, 'hephaestus/studio/dist');
const output = path.join(root, 'output/symmartys-rename-2026-10-28/browser');
await mkdir(output, { recursive: true });
const now = new Date().toISOString();
const evidence = { source: 'Synthetic register (browser test)', url: 'https://registry.example/company/42',
  fetched_at: now, sha256: 'a'.repeat(64) };
const signature = { algorithm: 'ed25519', value: 'synthetic-fixture-not-a-real-signature' };
const specs = [
  ['symmartys.company.lookup@v1', { country: { type: 'string', enum: ['NO', 'FR', 'CZ', 'FI'] }, number: { type: 'string', default: 'DO-NOT-USE-EXAMPLE' }, name: { type: 'string' } }, ['country']],
  ['symmartys.lei.lookup@v1', { lei: { type: 'string' }, name: { type: 'string' } }, []],
  ['symmartys.sanctions.screen@v1', { name: { type: 'string' }, address: { type: 'string' }, kind: { type: 'string' } }, []],
  ['symmartys.vat.check@v1', { vat: { type: 'string', default: 'DO-NOT-USE-EXAMPLE' }, requester_vat: { type: 'string' } }, ['vat']],
  ['symmartys.domain.rdap@v1', { domain: { type: 'string', default: 'example.com' } }, ['domain']],
  ['symmartys.eori.check@v1', { eori: { type: 'string', default: 'DO-NOT-USE-EXAMPLE' } }, []],
];
const manifest = { tools: specs.map(([capability_id, properties, required]) => ({
  product_id: 'symmartys', capability_id, name: capability_id, price_per_call_usd: .001,
  input_schema: { type: 'object', properties, required }, output_schema: { type: 'object' },
})) };
const requests = [];
const errors = [];
let mode = 'complete';
let paidRequest;
let paidFinished = false;
const terms = { chain_id: 8453, token: 'USDC', token_contract: '0x' + '1'.repeat(40), decimals: 6,
  pay_to: '0x' + '2'.repeat(40), offer_to: '0x' + '2'.repeat(40), amount_units: '1000', seller_units: '1000',
  fee_units: '0', fee_to: '0x' + '3'.repeat(40), eip712_name: 'USD Coin', eip712_version: '2', min_confirmations: 1 };
function resultFor(request, traceId) {
  const step_results = {};
  const steps = request.nodes.map((node) => {
    let facts;
    if (node.id === 'identity') facts = { found: true, companies: [{ name: 'Synthetic Counterparty AS', number: '42', status: 'ACTIVE' }], evidence };
    else if (node.id === 'sanctions' || node.id === 'wallet') facts = { listed: false, hits: [], lists: [
      { list: 'Synthetic sanctions list', published: '2026-10-27', fetched_at: now, sha256: ['b'.repeat(64)] },
    ] };
    else if (node.id === 'vat') facts = { valid: true, evidence };
    else if (node.id === 'domain') facts = { registered: true, age_days: 365, evidence: { ...evidence, fetched_at: '2026-01-01T00:00:00Z' } };
    else facts = { results: [{ valid: true }], evidence };
    const failed = mode === 'partial' && node.id === 'identity';
    const receipt = { nonce: `${node.id}-fixture`, signature };
    step_results[node.id] = { result: { output: failed ? { ok: false, error: 'synthetic_source_unavailable' } : facts,
      receipt: { ...receipt, nonce: 'provider-' + node.id } }, receipt };
    return { id: node.id, capability_id: node.capability_id, product_id: node.product_id,
      success: !failed, status_code: failed ? 503 : 200, price_usd: .001,
      result_sha256: 'c'.repeat(64), ...(failed ? { error: 'synthetic_source_unavailable' } : {}) };
  });
  return { trace_id: traceId, bill_of_materials: { steps, total_usd: .001 * steps.length, signature },
    step_results, final_result: Object.values(step_results).at(-1)?.result };
}
function paidState() {
  if (paidFinished) return { ...resultFor(paidRequest, 'tr_paid_synthetic'), status: 'completed', busy: false, next_step: null };
  return { trace_id: 'tr_paid_synthetic', status: 'prepared', busy: false, next_step: {
    id: 'identity', capability_id: 'symmartys.company.lookup@v1', source_hub: 'local', status: 'ready',
    quoted_usd: .001, terms, invoice: { nonce: '0x' + '4'.repeat(64), expires_at: Date.now() / 1000 + 3600 },
  } };
}
const json = (res, body) => { res.setHeader('content-type', 'application/json'); res.end(JSON.stringify(body)); };
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/ai-market/v2/manifest') return json(res, manifest);
    if (url.pathname === '/ai-market/v2/sandbox/quota') return json(res, { enabled: true, remaining: 10 });
    if (url.pathname === '/studio-ui-i18n.json') return json(res, { ui: {} });
    if (url.pathname === '/studio/preflight') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      paidRequest = JSON.parse(raw);
      return json(res, { ready: true, blockers: [], total_usd: .004, total_units: '4000',
        run_id: 'tr_paid_synthetic', access_token: 'offline-fixture',
        steps: [{ id: 'identity', capability_id: 'symmartys.company.lookup@v1', source_hub: 'local', quoted_usd: .004, status: 'ready', terms }] });
    }
    if (url.pathname === '/studio/paid-runs/tr_paid_synthetic/advance') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      if (JSON.parse(raw).tx_hash) paidFinished = true;
      return json(res, paidState());
    }
    if (url.pathname === '/studio/paid-runs/tr_paid_synthetic') return json(res, paidState());
    if (url.pathname === '/studio/run') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      const request = JSON.parse(raw); requests.push(request);
      return json(res, resultFor(request, 'tr_synthetic_' + requests.length));
    }
    if (!url.pathname.startsWith('/studio/')) { res.statusCode = 404; return res.end(); }
    const relative = url.pathname.slice('/studio/'.length) || 'index.html';
    const file = path.resolve(dist, relative);
    if (!file.startsWith(dist + path.sep)) { res.statusCode = 403; return res.end(); }
    const contents = await readFile(file);
    const extension = path.extname(file);
    res.setHeader('content-type', ({ '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' })[extension] || 'application/octet-stream');
    res.end(contents);
  } catch (error) { errors.push(String(error)); res.statusCode = 500; res.end(String(error)); }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  await page.addInitScript(() => {
    window.ethereum = { request: async ({ method }) => {
      if (method === 'eth_requestAccounts' || method === 'eth_accounts') return ['0x' + '5'.repeat(40)];
      if (method === 'eth_chainId') return '0x2105';
      if (method === 'eth_call') return '0x' + (1_000_000n).toString(16);
      if (method === 'eth_signTypedData_v4') return '0x' + '1'.repeat(128) + '1b';
      if (method === 'eth_sendTransaction') return '0x' + '6'.repeat(64);
      throw new Error('Unexpected synthetic wallet call: ' + method);
    } };
  });
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.route('**/*', (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  await page.goto(`${origin}/studio/?lang=ru`);
  await page.getByRole('button', { name: 'Wizards', exact: false }).click();
  await page.getByRole('menuitem', { name: /Проверить контрагента перед оплатой/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  await dialog.getByText('HEPHAESTUS / SYMMARTYS', { exact: true }).waitFor();
  assert.equal(await dialog.locator('input[name="vat"]').inputValue(), '');
  assert.equal(await dialog.locator('input[name="domain"]').inputValue(), '');
  assert.equal(await dialog.getByRole('button', { name: 'Выполнить проверки' }).isDisabled(), true);
  await dialog.locator('input[name="legalName"]').fill('Synthetic Counterparty AS');
  await dialog.locator('input[name="country"]').fill('NO');
  await dialog.locator('input[name="registrationNumber"]').fill('42');
  await dialog.locator('input[name="vat"]').fill('NO123456789');
  await dialog.locator('input[name="domain"]').fill('counterparty.example');
  await dialog.getByRole('button', { name: 'Выполнить проверки' }).click();
  await dialog.getByText('Запрошенные проверки завершены', { exact: true }).waitFor();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].continue_on_error, true);
  assert.equal(requests[0].nodes.length, 4);
  assert(requests[0].nodes.every((node) => node.product_id === 'symmartys' && node.capability_id.startsWith('symmartys.')));
  assert(requests[0].nodes.every((n) => n.depends_on.length === 0 && !n.input_from));
  assert(!JSON.stringify(requests).includes('DO-NOT-USE-EXAMPLE'));
  assert.equal(await dialog.locator('.cp-check').count(), 6);
  assert.equal(await dialog.locator('.cp-source a[href="https://registry.example/company/42"]').count(), 3);
  await dialog.getByText('Старше предела свежести', { exact: false }).waitFor();
  await dialog.evaluate((el) => { el.scrollTop = 0; });
  await page.screenshot({ path: path.join(output, 'fixture-desktop.png'), fullPage: true });
  const downloadEvent = page.waitForEvent('download');
  await dialog.getByRole('button', { name: /Скачать отчёт/ }).click();
  const downloaded = await downloadEvent;
  const report = JSON.parse(await readFile(await downloaded.path(), 'utf8'));
  assert.equal(report.signatureVerified, false);
  assert.equal(report.rawRun.step_results.identity.receipt.signature.value, signature.value);
  assert.equal(report.checks.find((check) => check.id === 'wallet').status, 'skipped');
  assert.deepEqual(report.checks.find((check) => check.id === 'wallet').facts, []);
  assert.equal(report.checks.find((check) => check.id === 'domain').sources[0].freshness, 'stale');
  mode = 'partial';
  await dialog.getByRole('button', { name: 'Выполнить проверки' }).click();
  await dialog.getByText('Отчёт неполный — проверьте ошибки и отсутствующие данные', { exact: true }).waitFor();
  assert.equal(await dialog.locator('.cp-check.cp-failed').count(), 1);
  assert.equal(await dialog.locator('.cp-check.cp-completed').count(), 3);
  await dialog.getByText('synthetic_source_unavailable', { exact: true }).waitFor();
  await dialog.locator('.cp-report').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'fixture-report.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await dialog.evaluate((el) => { el.scrollTop = 0; });
  assert.equal(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1), true);
  await page.screenshot({ path: path.join(output, 'fixture-mobile.png'), fullPage: true });
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  assert.equal(await dialog.isVisible(), false);
  await page.setViewportSize({ width: 1440, height: 1100 });
  mode = 'complete';
  await page.getByRole('button', { name: 'Wizards', exact: false }).click();
  await page.getByRole('menuitem', { name: /Проверить контрагента перед оплатой/ }).click();
  await dialog.getByRole('button', { name: 'Check payment', exact: true }).click();
  const paidDialog = page.getByRole('dialog', { name: 'Paid pipeline', exact: true });
  await paidDialog.getByRole('button', { name: 'Connect / refresh wallet', exact: true }).click();
  await paidDialog.getByRole('button', { name: 'Confirm budget and run', exact: true }).click();
  await paidDialog.getByText('Status: completed', { exact: false }).waitFor();
  await paidDialog.getByRole('button', { name: 'Close', exact: true }).click();
  await dialog.getByText('Запрошенные проверки завершены', { exact: true }).waitFor();
  await dialog.getByText('tr_paid_synthetic', { exact: false }).waitFor();
  const paidDownloadEvent = page.waitForEvent('download');
  await dialog.getByRole('button', { name: /Скачать отчёт/ }).click();
  const paidDownload = await paidDownloadEvent;
  const paidReport = JSON.parse(await readFile(await paidDownload.path(), 'utf8'));
  assert.equal(paidReport.traceId, 'tr_paid_synthetic');
  assert.equal(paidReport.input.legalName, 'Synthetic Counterparty AS');
  assert.equal(paidReport.checks.find((check) => check.id === 'identity').status, 'completed');
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, 'browser-check.json'), JSON.stringify({
    date: '2026-10-28', fixturesOnly: true, remoteRequests: false, requests: requests.length,
    simulatedPaidRuns: 1, realWalletOrPayments: false,
    productId: 'symmartys',
    checks: ['SYMMARTYS brand and capability IDs', 'Russian form and report', 'blank optional identifiers', 'single independent pipeline',
      'sources and freshness', 'original receipts in JSON download', 'partial failure with remaining results',
      '390px layout without horizontal overflow', 'dialog close', 'paid run returns to its original report snapshot (simulated wallet only)'], pageErrors: errors,
  }, null, 2) + '\n');
  console.log('Counterparty browser checks passed (offline fixtures; 2 trial runs + simulated paid run, desktop + 390px).');
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
