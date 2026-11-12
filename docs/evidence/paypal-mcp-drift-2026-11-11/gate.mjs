import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (!isObject(value)) return JSON.stringify(value);
  const entries = Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`);
  return `{${entries.join(',')}}`;
}

function digest(tools) {
  return createHash('sha256').update(canonicalJson(tools)).digest('hex');
}

function differences(before, after, path = '') {
  if (before === after) return [];
  if ((isObject(before) && isObject(after)) || (Array.isArray(before) && Array.isArray(after))) {
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...keys].sort().flatMap(key => {
      const segment = key.replaceAll('~', '~0').replaceAll('/', '~1');
      return differences(Object.hasOwn(before, key) ? before[key] : undefined,
        Object.hasOwn(after, key) ? after[key] : undefined, `${path}/${segment}`);
    });
  }
  if (before === undefined) return [{ op: 'add', path, after }];
  if (after === undefined) return [{ op: 'remove', path, before }];
  return [{ op: 'replace', path, before, after }];
}

try {
  assert.equal(process.argv.length, 3, 'Usage: node gate.mjs capture.json');
  const { lists } = JSON.parse(readFileSync(process.argv[2], 'utf8'));
  assert.deepEqual(lists.map(({ process, request }) => [process, request]), [[1, 1], [1, 2], [2, 1]]);
  for (const { tools } of lists) {
    assert(Array.isArray(tools) && tools.length > 0, 'Each capture must contain a nonempty tools array');
    assert(tools.every(tool => isObject(tool) && typeof tool.name === 'string' && isObject(tool.inputSchema)),
      'Each tool must have a name and an inputSchema object');
  }
  const comparisons = [[0, 1], [0, 2], [1, 2]].map(([before, after]) => ({
    from: { process: lists[before].process, request: lists[before].request },
    to: { process: lists[after].process, request: lists[after].request },
    changes: differences(lists[before].tools, lists[after].tools),
  }));
  const stable = comparisons.every(({ changes }) => changes.length === 0);
  const hashes = lists.map(({ process, request, tools }) => ({ process, request, sha256: digest(tools) }));
  console.log(JSON.stringify({ stable, hashes, comparisons }, null, 2));
  process.exitCode = stable ? 0 : 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}
