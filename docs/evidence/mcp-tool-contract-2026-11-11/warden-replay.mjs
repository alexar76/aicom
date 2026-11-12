import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(import.meta.url);
const folder = dirname(script);
const names = ['list_console_messages', 'list_network_requests', 'wait_for'];
const readJson = async (file) => JSON.parse(await readFile(file, 'utf8'));

async function serve(path) {
  const tools = await readJson(path);
  for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
    const message = JSON.parse(line);
    if (!Object.hasOwn(message, 'id')) continue;
    const response = { jsonrpc: '2.0', id: message.id };
    switch (message.method) {
      case 'initialize':
        response.result = { protocolVersion: '2025-06-18', capabilities: { tools: {} },
          serverInfo: { name: 'archived-tool-list-replay', version: '1' } };
        break;
      case 'tools/list':
        response.result = { tools };
        break;
      default:
        response.error = { code: -32601, message: 'Method not found' };
    }
    process.stdout.write(JSON.stringify(response) + '\n');
  }
}

async function replay(cli) {
  const temp = await mkdtemp(join(tmpdir(), 'warden-archive-replay-'));
  try {
    const active = join(temp, 'tools.json');
    const lock = join(temp, 'warden.lock.json');
    await writeFile(join(temp, '.mcp.json'), JSON.stringify({
      mcpServers: { archived: { command: process.execPath, args: [script, '--serve', active] } },
    }));

    async function select(phase) {
      const source = await readJson(join(folder, `observed.${phase}.json`));
      const tools = source.filter((tool) => names.includes(tool.name));
      assert.deepEqual(tools.map((tool) => tool.name).sort(), names);
      await writeFile(active, JSON.stringify(tools));
    }

    function scan(update = false) {
      const args = [cli, 'scan', '--project', '--cwd', temp, '--state-dir', join(temp, 'state'),
        '--lock', lock, '--timeout', '10000', '--json', '--fail-on-error'];
      if (update) args.push('--update-lock');
      const run = spawnSync(process.execPath, args, { encoding: 'utf8', timeout: 15_000, cwd: temp });
      if (run.error || !run.stdout.trim()) throw run.error || new Error(run.stderr);
      const report = JSON.parse(run.stdout);
      assert.equal(report.servers.length, 1);
      return { code: run.status, version: report.version, server: report.servers[0] };
    }

    await select('before');
    const created = scan(true);
    assert.equal(created.code, 0, JSON.stringify(created.server.findings));
    const pinned = await readFile(lock, 'utf8');
    const same = scan();
    assert.equal(same.code, 0, JSON.stringify(same.server.findings));
    assert.equal(same.server.allow, true);
    await select('after');
    const changed = scan();
    assert.equal(changed.code, 1);
    assert.equal(changed.server.lock?.state, 'drift');
    assert(changed.server.findings.some((finding) => finding.code === 'TOOL_DEF_DRIFT'));
    const changedTools = changed.server.lock.changes.map((change) => change.tool).sort();
    assert.deepEqual(changedTools, names);
    assert.equal(await readFile(lock, 'utf8'), pinned);
    console.log(JSON.stringify({ warden: changed.version, createExit: created.code, sameExit: same.code,
      changedExit: changed.code, finding: 'TOOL_DEF_DRIFT', changedTools, lockUnchanged: true }, null, 2));
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
}

if (process.argv[2] === '--serve') {
  await serve(process.argv[3]);
} else {
  if (process.argv.length !== 3) throw new Error('Usage: node warden-replay.mjs /path/to/warden/dist/mcp-server.js');
  await replay(resolve(process.argv[2]));
}
