import { existsSync } from 'node:fs';
import { createInterface } from 'node:readline';

const flagPath = process.argv[2];
if (!flagPath) {
  console.error('Usage: node approval-fixture.mjs <flag-file>');
  process.exit(1);
}

const toolNames = ['generate_layout', 'update_board'];
let destructiveHint = !existsSync(flagPath);
let initialized = false;

function send(message) {
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n');
}

const flagPoll = setInterval(() => {
  const nextHint = !existsSync(flagPath);
  if (nextHint === destructiveHint) return;
  destructiveHint = nextHint;
  if (initialized) send({ method: 'notifications/tools/list_changed' });
}, 250);

const input = createInterface({ input: process.stdin });
input.on('close', () => clearInterval(flagPoll));
input.on('line', (line) => {
  const { id, method, params } = JSON.parse(line);
  if (method === 'notifications/initialized') initialized = true;
  if (id === undefined) return;

  const result = (value) => send({ id, result: value });
  if (method === 'initialize') {
    const supported = ['2025-03-26', '2025-06-18', '2025-11-25'];
    return result({
      protocolVersion: supported.includes(params?.protocolVersion) ? params.protocolVersion : '2025-11-25',
      capabilities: { tools: { listChanged: true } },
      serverInfo: { name: 'histor-approval-fixture', version: '1.0.0' },
    });
  }
  if (method === 'ping') return result({});
  if (method === 'tools/list') {
    return result({
      tools: toolNames.map((name) => ({
        name,
        description: 'Return a fixed string without performing any operation.',
        inputSchema: { type: 'object', properties: {} },
        annotations: { readOnlyHint: false, destructiveHint },
      })),
    });
  }
  if (method === 'tools/call' && toolNames.includes(params?.name)) {
    return result({ content: [{ type: 'text', text: 'Fixture ran. No board or state changed.' }] });
  }
  send({ id, error: { code: -32601, message: 'Unknown method or tool' } });
});
