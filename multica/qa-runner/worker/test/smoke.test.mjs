import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { runSmoke, safeEnvironment } from '../smoke.mjs';

const LABELS = ['backend_health', 'modelmarket_https', 'hub_https'];

test('the fixed real targets run in parallel and output only the broker schema', async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const targets = [];
  const pending = runSmoke(async target => { targets.push(target); await gate; return 200; }, { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp' });
  assert.equal(targets.length, 3);
  assert.deepEqual(targets.map(target => target.hostname), ['backend', 'modelmarket.dev', 'hub.attestedmemory.net']);
  assert.equal(targets[0].path, '/health');
  assert.equal(targets[1].proxy.hostname, 'egress');
  assert.equal(targets[2].proxy.port, 8888);
  assert.ok(targets.every(target => target.timeoutMs === 3000));
  release();
  assert.deepEqual(await pending, { job: 'platform_smoke', checks: LABELS.map(name => ({ name, pass: true, status: 200 })), passed: true });
});

test('bad statuses, unreachable results and exceptions never leak remote data', async () => {
  let index = 0;
  const result = await runSmoke(async () => {
    index++;
    if (index === 1) return 500;
    if (index === 2) return 0;
    throw new Error('secret-in-untrusted-error');
  }, {});
  assert.deepEqual(result.checks.map(check => check.status), [500, 0, 0]);
  assert.equal(result.passed, false);
  assert.doesNotMatch(JSON.stringify(result), /secret-in-untrusted-error/);
});

test('unexpected credential or TLS environment fails before any network request', async () => {
  for (const environment of [{ GH_TOKEN: 'synthetic-never-print' }, { DEEPSEEK_API_KEY: 'synthetic-never-print' }, { NODE_OPTIONS: '--import=/tmp/unsafe.mjs' }, { NODE_TLS_REJECT_UNAUTHORIZED: '0' }]) {
    let called = false;
    const result = await runSmoke(async () => { called = true; return 200; }, environment);
    assert.equal(called, false);
    assert.equal(result.passed, false);
    assert.ok(result.checks.every(check => check.status === 0));
    assert.doesNotMatch(JSON.stringify(result), /synthetic|unsafe/);
  }
  assert.equal(safeEnvironment({ PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp', HTTP_PROXY: 'http://egress:8888', npm_lifecycle_event: 'smoke' }), true);
});

test('caller arguments cannot substitute a URL or command', async () => {
  let called = false;
  const result = await runSmoke(async () => { called = true; return 200; }, {}, ['https://attacker.invalid/', '; echo arbitrary']);
  assert.equal(called, false);
  assert.equal(result.passed, false);
  assert.deepEqual(result.checks.map(check => check.name), LABELS);
  assert.doesNotMatch(JSON.stringify(result), /attacker|arbitrary/);
});

test('CLI rejects inherited secret environment with strict JSON and no raw stderr', async () => {
  await assert.rejects(promisify(execFile)(process.execPath, [fileURLToPath(new URL('../smoke.mjs', import.meta.url))], {
    env: { PATH: process.env.PATH, HOME: '/tmp', GITHUB_TOKEN: 'synthetic-secret-does-not-belong-in-worker' }, timeout: 3000,
  }), error => {
    assert.equal(error.code, 1);
    assert.equal(error.stderr, '');
    const result = JSON.parse(error.stdout);
    assert.deepEqual(Object.keys(result), ['job', 'checks', 'passed']);
    assert.deepEqual(result.checks.map(check => check.name), LABELS);
    assert.equal(result.passed, false);
    assert.doesNotMatch(error.stdout, /synthetic|TOKEN/);
    return true;
  });
});
