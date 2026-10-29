import { readFileSync, writeFileSync, appendFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { trajectory, hash } from './study.mjs';

const plan = JSON.parse(readFileSync('/out/frozen-before-api.json', 'utf8'));
const cases = new Map(JSON.parse(readFileSync('/study/cases.json', 'utf8')).cases.map(c => [c.pair_id, c]));
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
const iterator = lines[Symbol.asyncIterator]();
const results = [];
try {
  for (const slot of plan.slots) {
    const c = cases.get(slot.pair_id);
    const result = await trajectory(c, slot, async (requestBody, attempt, signal) => {
      if (signal.aborted) throw Error('cancelled');
      const requestId = hash(JSON.stringify({ plan: plan.planId, slot: slot.slot_id, attempt })).slice(0, 32);
      process.stdout.write(JSON.stringify({ event: 'call', requestId, slotId: slot.slot_id, attempt, body: requestBody }) + '\n');
      const next = await iterator.next();
      if (next.done) throw Error('relay ended');
      const response = JSON.parse(next.value);
      if (response.requestId !== requestId) throw Error('response binding');
      if (response.status !== 'ok' || signal.aborted) throw Error('generation failed');
      return { answer: response.answer, requestId };
    });
    appendFileSync('/out/trajectories.jsonl', JSON.stringify(result) + '\n');
    results.push(result);
    process.stdout.write(JSON.stringify({ event: 'trajectory', slotId: slot.slot_id, completed: results.length, planned: plan.slots.length,
      population: slot.population, status: result.result.status, calls: result.proposals.filter(p => !p.synthetic).length }) + '\n');
  }
  writeFileSync('/out/worker-complete.json', JSON.stringify({ completed: results.length, planned: plan.slots.length }) + '\n');
} finally { lines.close(); }
