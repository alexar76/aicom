import readline from 'node:readline';
import { readFileSync, appendFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const trace = fileURLToPath(new URL('./requests.jsonl', import.meta.url));
const description = () => readFileSync(new URL('./description.txt', import.meta.url), 'utf8').trim();
for await (const line of readline.createInterface({ input: process.stdin })) {
  const req = JSON.parse(line);
  appendFileSync(trace, JSON.stringify({ method: req.method }) + '\n');
  if (req.id === undefined) continue;
  let result;
  if (req.method === 'initialize') result = {
    protocolVersion: '2025-06-18', capabilities: { tools: {} },
    serverInfo: { name: 'console-hn-synthetic-notes', version: '1.0.0' }
  };
  else if (req.method === 'tools/list') result = { tools: [{
    name: 'get_note', description: description(),
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] }
  }] };
  else {
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: req.id,
      error: { code: -32601, message: 'Method not found' } }) + '\n');
    continue;
  }
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: req.id, result }) + '\n');
}
