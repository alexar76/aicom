import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import { networkInterfaces } from 'node:os';
import { createInterface } from 'node:readline';
import { setTimeout as delay } from 'node:timers/promises';

const entry = new URL('./node_modules/@paypal/mcp/dist/index.js', import.meta.url);
const args = ['--tools=transactions.list', '--paypal-environment=sandbox'];
const protocolVersion = '2025-03-26';
const methods = ['initialize', 'notifications/initialized', 'tools/list'];

async function verifyIsolation() {
  assert.equal(process.platform, 'linux');
  assert.equal(process.getuid(), 65534);
  const status = readFileSync('/proc/self/status', 'utf8');
  assert.match(status, /^CapEff:\s+0+$/m);
  assert.match(status, /^NoNewPrivs:\s+1$/m);
  const interfaces = networkInterfaces();
  assert.deepEqual(Object.keys(interfaces), ['lo']);
  assert(interfaces.lo.every(address => address.internal));

  const networkError = await new Promise((resolve, reject) => {
    const socket = net.connect({ host: '198.18.0.1', port: 9 });
    socket.setTimeout(1000, () => socket.destroy(new Error('TCP probe timed out')));
    socket.once('connect', () => {
      socket.destroy();
      reject(new Error('TCP probe unexpectedly connected'));
    });
    socket.once('error', error => resolve(error.code));
  });
  assert.equal(networkError, 'ENETUNREACH');
  const writeProbes = {};
  for (const directory of ['/tmp', '/replay']) {
    assert.throws(() => writeFileSync(`${directory}/.paypal-replay-write-probe`, '', { flag: 'wx' }), error => {
      writeProbes[directory] = error.code;
      return error.code === 'EROFS';
    });
  }
  return { uid: process.getuid(), effectiveCapabilities: 0, noNewPrivileges: true,
    interfaces: Object.keys(interfaces), networkError, writeProbes };
}

async function captureProcess(processNumber, listCount) {
  const child = spawn(process.execPath, [entry.pathname, ...args], {
    env: { PAYPAL_ACCESS_TOKEN: 'placeholder-for-schema-only', PAYPAL_ENVIRONMENT: 'SANDBOX', TZ: 'UTC' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  const exited = once(child, 'close');
  let stderr = '';
  let id = 0;
  child.stderr.setEncoding('utf8').on('data', chunk => { stderr += chunk; });

  function send(method, params, requestId) {
    assert(methods.includes(method));
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: requestId, method, params }) + '\n');
  }

  async function request(method, params) {
    id += 1;
    send(method, params, id);
    const timeout = new AbortController();
    try {
      const message = await Promise.race([
        lines.next(),
        delay(30_000, undefined, { signal: timeout.signal }).then(() => {
          throw new Error(`${method} timed out. ${stderr.trim()}`);
        }),
      ]);
      assert(!message.done, `${method} ended without a response. ${stderr.trim()}`);
      const response = JSON.parse(message.value);
      assert.equal(response.id, id);
      assert.equal(response.jsonrpc, '2.0');
      assert.equal(response.error, undefined, JSON.stringify(response.error));
      return response.result;
    } finally {
      timeout.abort();
    }
  }

  try {
    const handshake = await request('initialize', {
      protocolVersion, capabilities: {}, clientInfo: { name: 'paypal-schema-replay', version: '1.0.0' },
    });
    assert.equal(handshake.protocolVersion, protocolVersion);
    assert(handshake.capabilities.tools);
    send('notifications/initialized');
    const lists = [];
    for (let listNumber = 1; listNumber <= listCount; listNumber += 1) {
      const result = await request('tools/list', {});
      assert.equal(result.nextCursor, undefined);
      assert.deepEqual(result.tools.map(tool => tool.name), ['list_transactions']);
      lists.push({ process: processNumber, request: listNumber, receivedAt: new Date().toISOString(), tools: result.tools });
      if (listNumber < listCount) await delay(50);
    }
    assert.match(stderr, /Mode: Sandbox/);
    return { server: handshake.serverInfo, lists };
  } finally {
    child.kill('SIGKILL');
    await exited;
  }
}

function installedVersion(name) {
  return JSON.parse(readFileSync(new URL(`./node_modules/${name}/package.json`, import.meta.url), 'utf8')).version;
}

const isolation = await verifyIsolation();
const first = await captureProcess(1, 2);
const restarted = await captureProcess(2, 1);
assert.deepEqual(restarted.server, first.server);
console.log(JSON.stringify({
  packages: {
    '@paypal/mcp': installedVersion('@paypal/mcp'),
    '@paypal/agent-toolkit': installedVersion('@paypal/agent-toolkit'),
    '@modelcontextprotocol/sdk': installedVersion('@modelcontextprotocol/sdk'),
  },
  runtime: { node: process.version, platform: process.platform, architecture: process.arch, timezone: 'UTC' },
  isolation,
  protocolVersion,
  server: first.server,
  args,
  methods,
  lists: [...first.lists, ...restarted.lists],
}, null, 2));
