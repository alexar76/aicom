// Installs the exact 0.22.3 archive (and the published 0.22.2 archive kept in
// ../histor-warden-release-2026-10-27/warden as the control) into throwaway consumers,
// offline and without lifecycle scripts, and checks what 0.22.3 changes.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const evidence = dirname(fileURLToPath(import.meta.url));
const root = resolve(evidence, '../../..');
const artifact = JSON.parse(readFileSync(join(evidence, 'artifact.json'), 'utf8'));
const control = join(evidence, '../histor-warden-release-2026-10-27/warden/aimarket-warden-0.22.2.tgz');
// HISTOR's answer for this set on 2026-11-01 10:35Z (query.toolSetDigest, no digestError): see README.
const HISTOR_DIGEST = 'sha256-0myjesiTMvVJ9vLScE4PlNlO+d0Z8zmRzWqiB//+i30=';
const tools = [
  { name: 'set_ratio', description: 'Set a ratio between 0 and 1.',
    inputSchema: { type: 'object', properties: { ratio: { type: 'number', default: 0.5, minimum: 1e-7 } } } },
  { name: 'set_ratio', description: 'Duplicate name.',
    inputSchema: { type: 'object', properties: { big: { type: 'integer', default: 12345678901234567890 } } } },
];

function sha256(file) { return createHash('sha256').update(readFileSync(file)).digest('hex'); }
function buildDigest(dir) {
  const hash = createHash('sha256');
  for (const name of readdirSync(join(dir, 'dist')).filter(n => n.endsWith('.js')).sort())
    hash.update(name + '\0').update(readFileSync(join(dir, 'dist', name))).update('\0');
  return hash.digest('hex');
}

async function install(archive) {
  mkdirSync(join(root, 'build'), { recursive: true });
  const consumer = mkdtempSync(join(root, 'build/warden-clean-consumer-'));
  const state = join(consumer, 'state');
  mkdirSync(state);
  writeFileSync(join(consumer, 'package.json'), JSON.stringify({ private: true, type: 'module' }) + '\n');
  const env = { PATH: process.env.PATH, npm_config_cache: join(root, 'build/npm-cache-warden-release'),
    WARDEN_STATE_DIR: state, WARDEN_ALLOW_PIN_CHANGES: '0' };
  const r = spawnSync('npm', ['install', '--offline', '--ignore-scripts', '--no-audit', '--no-fund',
    '--package-lock=false', '--save=false', archive], { cwd: consumer, env, encoding: 'utf8', timeout: 60_000 });
  assert.equal(r.status, 0, r.stderr);
  const dir = join(consumer, 'node_modules/@aimarket/warden');
  return { consumer, state, env, dir, bin: join(consumer, 'node_modules/.bin/warden-mcp'),
    pkg: JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')) };
}

async function behaviour(c) {
  const mtl = await import(pathToFileURL(join(c.dir, 'dist/mtl.js')).href);
  let digest, digestError;
  try { digest = mtl.mtlToolSetDigest(tools); } catch (e) { digestError = e.code ?? e.message; }
  const empty = (() => { try { return mtl.mtlToolSetDigest([]); } catch (e) { return e.code ?? e.message; } })();
  const histor = await import(pathToFileURL(join(c.dir, 'dist/histor.js')).href);
  const ua = typeof histor.historUserAgent === 'function'
    ? { person: histor.historUserAgent(c.pkg.version, {}), github: histor.historUserAgent(c.pkg.version, { GITHUB_ACTIONS: 'true' }),
        gitlab: histor.historUserAgent(c.pkg.version, { GITLAB_CI: 'true' }), ci: histor.historUserAgent(c.pkg.version, { CI: '1' }) }
    : null;
  const help = spawnSync(process.execPath, [c.bin, '--help'], { cwd: c.consumer, env: c.env, encoding: 'utf8', timeout: 10_000 });
  return { version: c.pkg.version, buildDigest: buildDigest(c.dir), digest, digestError, emptySet: empty, userAgent: ua,
    help: { status: help.status, firstLine: (help.stdout || help.stderr).split('\n')[0] } };
}

assert.equal(sha256(join(evidence, artifact.filename)), artifact.sha256);
const next = await install(join(evidence, artifact.filename));
assert.equal(next.pkg.version, '0.22.3');
for (const field of ['dependencies', 'peerDependencies', 'optionalDependencies']) assert.equal(Object.keys(next.pkg[field] ?? {}).length, 0);
const library = await import(pathToFileURL(join(next.dir, 'dist/index.js')).href);
assert.equal(typeof library.Warden, 'function');
assert.equal(typeof library.StaticScanGate, 'function');

const fixture = join(next.consumer, 'mcp-empty.json');
writeFileSync(fixture, '{"mcpServers":{}}\n');
const scan = spawnSync(process.execPath, [next.bin, 'scan', '--no-launch', '--json', fixture], { cwd: next.consumer, env: next.env, encoding: 'utf8', timeout: 10_000 });
assert.equal(scan.status, 0, scan.stderr);
const init = spawnSync(process.execPath, [next.bin], { cwd: next.consumer, env: next.env, encoding: 'utf8', timeout: 10_000,
  input: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'release-check', version: '1' } } }) + '\n' });
assert.equal(init.status, 0, init.stderr);
const initialize = JSON.parse(init.stdout.trim()).result;
assert.equal(initialize.serverInfo.version, '0.22.3');

const now = await behaviour(next);
assert.equal(now.buildDigest, artifact.buildDigest);
assert.equal(now.digest, HISTOR_DIGEST, 'MTL/1.1 digest must equal HISTOR\'s');
assert.match(now.emptySet, /^sha256-/);
assert.deepEqual(now.userAgent, { person: 'warden-scan/0.22.3', github: 'warden-scan/0.22.3 (ci; github-actions)',
  gitlab: 'warden-scan/0.22.3 (ci; gitlab)', ci: 'warden-scan/0.22.3 (ci)' });
assert.equal(now.help.status, 0);
assert.match(now.help.firstLine, /^Usage: warden-mcp/);
assert.deepEqual(readdirSync(next.state), []);

const before = await behaviour(await install(control));
assert.equal(before.version, '0.22.2');
assert.equal(before.digest, undefined, '0.22.2 should refuse the fractional set');

const result = { archive: artifact.filename, sha256: artifact.sha256, offline_install: true, install_scripts_disabled: true,
  runtime_dependencies: 0, library_import: true, cli_scan_exit: scan.status, mcp_initialize_version: initialize.serverInfo.version,
  state_unchanged: true, release: now, control_published_0_22_2: before, histor_digest_2026_11_01: HISTOR_DIGEST };
writeFileSync(join(evidence, 'clean-consumer.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ release: { digest: now.digest, help: now.help.firstLine },
  control: { digestError: before.digestError, emptySet: before.emptySet, help: before.help } }));
