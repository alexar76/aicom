import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';

const evidence = dirname(fileURLToPath(import.meta.url));
const root = resolve(evidence, '../../../..');
const artifact = JSON.parse(readFileSync(join(evidence, 'artifact.json'), 'utf8'));
const archive = join(evidence, artifact.filename);
assert.equal(createHash('sha256').update(readFileSync(archive)).digest('hex'), artifact.sha256);
mkdirSync(join(root, 'build'), { recursive: true });
const consumer = mkdtempSync(join(root, 'build/warden-clean-consumer-'));
const state = join(consumer, 'state');
mkdirSync(state);
writeFileSync(join(consumer, 'package.json'), JSON.stringify({ private: true, type: 'module' }) + '\n');
const env = {
  PATH: process.env.PATH,
  npm_config_cache: join(root, 'build/npm-cache-warden-release'),
  WARDEN_STATE_DIR: state,
  WARDEN_ALLOW_PIN_CHANGES: '0',
};
// Installation uses packed JS only, with no lifecycle scripts or network access.
// Release build/prepare and all publication checks are separate recorded steps.
const install = spawnSync('npm', ['install', '--offline', '--ignore-scripts', '--no-audit', '--no-fund', '--package-lock=false', '--save=false', archive], {
  cwd: consumer, env, encoding: 'utf8', timeout: 30_000,
});
assert.equal(install.status, 0, install.stderr);
const installed = join(consumer, 'node_modules/@aimarket/warden');
const pkg = JSON.parse(readFileSync(join(installed, 'package.json'), 'utf8'));
assert.equal(pkg.version, '0.22.2');
for (const field of ['dependencies', 'peerDependencies', 'optionalDependencies']) assert.equal(Object.keys(pkg[field] ?? {}).length, 0);
const library = await import(pathToFileURL(join(installed, 'dist/index.js')).href);
assert.equal(typeof library.Warden, 'function');
assert.equal(typeof library.StaticScanGate, 'function');
const bin = join(consumer, 'node_modules/.bin/warden-mcp');
const fixture = join(consumer, 'mcp-empty.json');
writeFileSync(fixture, '{"mcpServers":{}}\n');
const cli = spawnSync(process.execPath, [bin, 'scan', '--no-launch', '--json', fixture], { cwd: consumer, env, encoding: 'utf8', timeout: 10_000 });
assert.equal(cli.status, 0, cli.stderr);
const cliResult = JSON.parse(cli.stdout);
const server = { id: 'release-contract', name: 'Synthetic release fixture', transport: 'http', url: 'https://fixture.invalid/mcp' };
const tools = [{ name: 'fixture_read', description: 'Read synthetic fixture data.', inputSchema: { type: 'object', properties: {} } }];
let id = 0;
function rpc(method, params) {
  const request = { jsonrpc: '2.0', id: ++id, method, ...(params ? { params } : {}) };
  const child = spawnSync(process.execPath, [bin], { cwd: consumer, env, encoding: 'utf8', timeout: 10_000, input: JSON.stringify(request) + '\n' });
  assert.equal(child.status, 0, child.stderr);
  const lines = child.stdout.trim().split('\n');
  assert.equal(lines.length, 1);
  const response = JSON.parse(lines[0]);
  assert.equal(response.id, request.id);
  assert.equal(response.error, undefined);
  return response.result;
}
const initialize = rpc('initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'release-check', version: '1' } });
assert.equal(initialize.serverInfo.version, '0.22.2');
const listed = rpc('tools/list').tools;
assert.equal(listed.length, 9);
const shapes = [
  ['omitted', {}],
  ['null', { server_info: null }],
  ['empty', { server_info: {} }],
  ['name', { server_info: { name: 'fixture' } }],
  ['version', { server_info: { version: '1.0.0' } }],
  ['full', { server_info: { name: 'fixture', version: '1.0.0' } }],
];
for (const [, extra] of shapes) {
  const status = rpc('tools/call', { name: 'status_mcp_server', arguments: { server, tools, ...extra } });
  assert.notEqual(status.isError, true);
  assert.equal(status.structuredContent.previous, null);
  assert.equal(status.structuredContent.mutationsEnabled, false);
}
const badKeys = ['extra', '__proto__', 'constructor'];
for (const key of badKeys) {
  const info = JSON.parse(`{"name":"fixture","version":"1.0.0",${JSON.stringify(key)}:true}`);
  const status = rpc('tools/call', { name: 'status_mcp_server', arguments: { server, tools, server_info: info } });
  assert.equal(status.isError, true);
  assert.equal(status.structuredContent, undefined);
  assert.equal(status.content[0].text, 'server_info may contain only name and version');
}
assert.deepEqual(readdirSync(state), []);
const result = {
  archive: artifact.filename, sha256: artifact.sha256, version: pkg.version,
  offline_install: true, install_scripts_disabled: true, runtime_dependencies: 0,
  library_import: true, cli_scan: cliResult, protocol: initialize.protocolVersion,
  tool_count: listed.length, compatible_server_info_shapes: shapes.map(([name]) => name),
  rejected_unknown_keys: badKeys, state_unchanged: true,
};
writeFileSync(join(evidence, 'clean-consumer.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ version: result.version, tool_count: result.tool_count, compatible_shapes: shapes.length, rejected_keys: badKeys.length, state_unchanged: true }));
