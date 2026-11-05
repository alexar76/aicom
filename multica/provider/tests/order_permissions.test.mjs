// The order agent's OpenCode bash rules (order-task/opencode-order-agent.json), evaluated the way OpenCode 1.18.32
// does: every command in the line is checked separately (tool/shell.ts walks all `command` nodes, including those
// inside $(...), backticks and pipes); a redirected command is checked with its redirect; the last matching rule
// wins (permission/index.ts evaluate -> findLast); match() below is packages/core/src/util/wildcard.ts verbatim.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function match(input, pattern) {
  const normalized = input.replaceAll('\\', '/');
  let escaped = pattern
    .replaceAll('\\', '/')
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.');
  if (escaped.endsWith(' .*')) escaped = escaped.slice(0, -3) + '( .*)?';
  return new RegExp('^' + escaped + '$', 's').test(normalized);
}

const config = JSON.parse(readFileSync(new URL('../order-task/opencode-order-agent.json', import.meta.url), 'utf8'));
const rules = Object.entries(config.permission.bash);
const action = (pattern) => (rules.findLast(([p]) => match(pattern, p)) ?? ['', 'ask'])[1];
const W = '/home/node/tools/order/order-task';

test('the two wrapper forms are allowed', () => {
  assert.equal(action(`${W} get MY-65`), 'allow');
  assert.equal(action(`${W} done 0d3c3a7e-0000-4000-8000-000000000001`), 'allow');
});

test('everything else is denied', () => {
  for (const p of [
    'multica issue get MY-1 --output json', 'multica issue status MY-1 done --no-start', 'multica issue comment list MY-1',
    'cat /home/node/.multica/config.json', 'curl https://example.com', 'sh -c id', 'env', `~/tools/order/order-task get MY-1`,
    `${W}x get MY-1`, `/tmp/order-task get MY-1`,
  ]) assert.equal(action(p), 'deny', p);
});

test('redirects, $ and backticks in the wrapper line are denied', () => {
  for (const p of [
    `${W} get MY-1 > /home/node/.config/opencode/opencode.jsonc`, `${W} get MY-1 >> /home/node/.bashrc`,
    `${W} get MY-1 2>/home/node/.multica/config.json`, `${W} get MY-1 &> x`, `${W} get MY-1 < /etc/passwd`,
    `${W} get $(cat /home/node/.multica/config.json)`, `${W} get \`id\``, `${W} get $HOME`, `${W} get MY-1 <<< x`,
  ]) assert.equal(action(p), 'deny', p);
});

test('a chained or nested command is checked on its own and denied', () => {
  // OpenCode asks for each command node; one deny refuses the whole call.
  for (const inner of ['touch /tmp/x', 'sh -c id', 'cat /home/node/.multica/config.json']) assert.equal(action(inner), 'deny');
});
