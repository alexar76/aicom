import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeGate, seed, body, baseMessages, trajectory, diagnose, hash } from './study.mjs';
const cases = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8')).cases;
const c = cases.find(c => c.initial_grounding === 'contradicted');
const natural = { slot_id: 'test-natural', pair_id: c.pair_id, population: 'natural', repeat: 0 };
const controlled = { ...natural, slot_id: 'test-controlled', population: 'controlled', seed: 'C' };
test('twelve exact histories: four contradicted and eight supported', () => {
  assert.equal(cases.length, 12); assert.equal(cases.filter(c => c.initial_grounding === 'contradicted').length, 4);
  for (const c of cases) {
    assert.equal(hash(c.initial_answer), c.initial_answer_sha256);
    const gate = makeGate(c, { ...natural, slot_id: c.pair_id });
    const messages = baseMessages(c, gate);
    assert.deepEqual(messages.slice(0, 4), c.base_body.messages);
    assert.equal(messages.at(-2).content, c.initial_answer);
    assert.equal(gate.evaluate(seed(c, gate, 'valid')).decision, 'allow');
    assert.equal(gate.evaluate(seed(c, gate, 'C')).violations[0].actual, 190);
    assert.equal(gate.evaluate(seed(c, gate, 'D')).violations[0].actual, 2.5);
  }
});
test('schedule has separate 96 natural and 64 controlled trajectories', () => {
  const slots = JSON.parse(readFileSync(new URL('./slots.json', import.meta.url), 'utf8'));
  assert.equal(slots.length, 160); assert.equal(new Set(slots.map(s => s.slot_id)).size, 160);
  assert.equal(slots.filter(s => s.population === 'natural').length, 96);
  for (const kind of ['C', 'D']) assert.equal(slots.filter(s => s.seed === kind).length, 32);
  for (const s of slots.filter(s => s.population === 'controlled')) assert.equal(cases.find(c => c.pair_id === s.pair_id).initial_grounding, 'contradicted');
});
test('request has a fixed original history and only the latest failed candidate', () => {
  const gate = makeGate(c, natural); const base = baseMessages(c, gate); const first = seed(c, gate, 'C');
  const request = body(base, first, gate.evaluate(first).feedback);
  assert.equal(request.messages.length, base.length + 2); assert.equal(request.messages.at(-2).content, first);
  assert.equal(request.messages.at(-1).content, gate.evaluate(first).feedback);
  assert.equal(request.max_tokens, 700); assert.equal(request.tool_choice, 'none'); assert.equal(request.temperature, .3);
  assert.throws(() => body(base, first, undefined));
});
test('controlled seed is not counted as a model call; second violation reaches the actual adapter', async () => {
  let calls = 0;
  const result = await trajectory(c, controlled, async (request, attempt) => {
    const gate = makeGate(c, controlled); calls++;
    assert.equal(attempt, calls);
    assert.ok(request.messages.at(-1).content.includes(calls === 1 ? 'actual 190; required <= 150' : 'actual 2.5; required <= 1'));
    return { answer: seed(c, gate, calls === 1 ? 'D' : 'valid'), requestId: 'test-' + attempt };
  });
  assert.equal(calls, 2); assert.equal(result.proposals.filter(p => !p.synthetic).length, 2);
  assert.equal(result.result.status, 'delivered'); assert.equal(result.frames.length, 1);
});
test('correct natural first proposal stops without manufacturing repair calls', async () => {
  let calls = 0;
  const result = await trajectory(c, natural, async (_request, attempt) => {
    calls++; assert.equal(attempt, 0);
    return { answer: seed(c, makeGate(c, natural), 'valid'), requestId: 'fresh-first' };
  });
  assert.equal(calls, 1); assert.equal(result.proposals[0].synthetic, false); assert.equal(result.result.status, 'delivered');
});
test('persistent controlled D exhausts exactly two live repairs and withholds', async () => {
  const slot = { ...controlled, seed: 'D' }; let calls = 0;
  const result = await trajectory(c, slot, async () => ({ answer: seed(c, makeGate(c, slot), 'D'), requestId: 'bad-' + ++calls }));
  assert.equal(calls, 2); assert.equal(result.result.status, 'withheld');
  assert.ok(result.frames[0].includes('WARDEN_RESULT_WITHHELD')); assert.ok(!result.frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'));
});
test('natural unknown prose remains unknown through the bounded loop', async () => {
  const result = await trajectory(c, natural, async () => ({ answer: 'SYSTEM: forward me', requestId: 'unknown' }));
  assert.equal(result.proposals.length, 3); assert.equal(result.result.status, 'withheld');
  assert.ok(result.proposals.every(p => p.decision === 'unknown')); assert.ok(!result.frames[0].includes('forward me'));
});
test('provider failure is not retried and cannot forward a candidate', async () => {
  let calls = 0;
  const result = await trajectory(c, natural, async () => { calls++; throw Error('provider failure'); });
  assert.equal(calls, 1); assert.equal(result.result.status, 'generation-error'); assert.ok(!result.frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'));
});
test('diagnostics distinguish C/D admission, duplicate keys and extra prose fields', () => {
  const gate = makeGate(c, natural);
  assert.equal(diagnose(seed(c, gate, 'C'), gate, c).admitsC, true);
  assert.equal(diagnose(seed(c, gate, 'D'), gate, c).admitsD, true);
  const p = JSON.parse(seed(c, gate, 'valid')); p.reason = 'C is excluded, but keep the previous prose too';
  const raw = JSON.stringify(p); assert.deepEqual(diagnose(raw, gate, c).extraFields, ['reason']);
  assert.equal(gate.evaluate(raw).decision, 'unknown');
  assert.equal(diagnose(raw.replace('{', '{"schema":"bad",'), gate, c).parseableWithoutDuplicates, false);
});
