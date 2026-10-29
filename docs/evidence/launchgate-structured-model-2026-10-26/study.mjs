import { createHash } from 'node:crypto';
import { createAnswerGate } from './runtime/answer-gate.js';
import { parseJsonStrict } from './runtime/jcs.js';

export const hash = text => createHash('sha256').update(text).digest('hex');
export function makeGate(c, slot) {
  const fields = [...new Set([...c.fixture.criterion.constraints.map(r => r.field), c.fixture.criterion.rank_by.field])];
  return createAnswerGate({ sessionId: slot.slot_id, turn: 1, disclosure: 'source-instructions',
    rules: c.fixture.criterion.constraints,
    records: c.fixture.records.map(r => ({ id: r.id, attributes: Object.fromEntries(fields.map(f => [f, r[f]])) })),
    ranking: { field: c.fixture.criterion.rank_by.field, direction: c.fixture.criterion.rank_by.direction === 'asc' ? 'min' : 'max' } });
}
export function eligibleIds(c) {
  return c.fixture.records.filter(r => c.fixture.criterion.constraints.every(rule => rule.op === 'eq'
    ? typeof r[rule.field] === typeof rule.value && r[rule.field] === rule.value
    : rule.op === 'lte' ? r[rule.field] <= rule.value : r[rule.field] >= rule.value)).map(r => r.id);
}
export function seed(c, gate, kind) {
  if (!['C', 'D', 'valid'].includes(kind)) throw Error('invalid seed kind');
  const eligible = eligibleIds(c); const selected = JSON.parse(c.initial_answer).selected_hotel_id;
  if (!eligible.includes(selected)) throw Error('inadmissible original selection');
  const extra = kind === 'valid' ? [] : [c.fixture.records.find(r => r.id.endsWith('-' + kind)).id];
  return JSON.stringify({ schema: 'warden-selection/1', catalogSha256: gate.catalog.catalogSha256,
    selectedRef: gate.referenceForRecord(selected), eligibleRefs: [...eligible, ...extra].map(id => gate.referenceForRecord(id)) });
}
export function baseMessages(c, gate) {
  if (c.base_body.messages.length !== 4 || hash(c.initial_answer) !== c.initial_answer_sha256) throw Error('invalid saved context');
  const instruction = 'Replace the preceding answer entirely with one JSON object using this new output contract. '
    + 'The host catalog below is the normalized captured snapshot for the user constraints. Evaluate every rule for every record. '
    + 'Return exactly schema, catalogSha256, selectedRef and eligibleRefs; schema must be "warden-selection/1", '
    + 'catalogSha256 must equal the catalog digest, selectedRef must be one optimal eligible record reference, '
    + 'eligibleRefs must list ALL and ONLY eligible references. No reason, extra fields, prices, prose or duplicate keys. '
    + 'The host independently preserves its source-instruction notice.\nHOST_CATALOG\n' + JSON.stringify(gate.catalog);
  return [...c.base_body.messages, { role: 'assistant', content: c.initial_answer }, { role: 'user', content: instruction }];
}
export function body(base, previous, feedback) {
  if ((previous === undefined) !== (feedback === undefined)) throw Error('incomplete repair pair');
  const messages = previous === undefined ? [...base] : [...base, { role: 'assistant', content: previous }, { role: 'user', content: feedback }];
  return { messages, temperature: .3, max_tokens: 700, response_format: { type: 'json_object' }, tool_choice: 'none',
    tools: [{ type: 'function', function: { name: 'mcp__records__get_records', description: 'Returns the hotel listing records.', parameters: { type: 'object', properties: {}, additionalProperties: false } } }] };
}
export function diagnose(raw, gate, c) {
  let parsed;
  try { parsed = parseJsonStrict(raw); } catch { return { parseableWithoutDuplicates: false, admitsC: null, admitsD: null, extraFields: null }; }
  const object = parsed && typeof parsed === 'object' && !Array.isArray(parsed);
  const list = object && Array.isArray(parsed.eligibleRefs) ? parsed.eligibleRefs : [];
  const ref = suffix => gate.referenceForRecord(c.fixture.records.find(r => r.id.endsWith('-' + suffix)).id);
  return { parseableWithoutDuplicates: true, admitsC: list.includes(ref('C')), admitsD: list.includes(ref('D')),
    extraFields: object ? Object.keys(parsed).filter(k => !['schema', 'catalogSha256', 'selectedRef', 'eligibleRefs'].includes(k)) : null };
}
export async function trajectory(c, slot, call) {
  const gate = makeGate(c, slot); const base = baseMessages(c, gate); const proposals = []; const frames = [];
  let previous;
  const result = await gate.run({ maxCorrections: 2, timeoutMs: 120000,
    generate: async request => {
      const synthetic = slot.population === 'controlled' && request.attempt === 0;
      let raw; let requestId = null;
      if (synthetic) raw = seed(c, gate, slot.seed);
      else {
        const requestBody = body(base, request.attempt === 0 ? undefined : previous, request.feedback);
        const received = await call(requestBody, request.attempt, request.signal);
        raw = received.answer; requestId = received.requestId;
      }
      previous = raw;
      const d = gate.evaluate(raw);
      proposals.push({ attempt: request.attempt, synthetic, requestId, answer: raw, answerSha256: hash(raw),
        decision: d.decision, code: d.code, violations: d.violations, diagnostics: diagnose(raw, gate, c) });
      return raw;
    },
    emit: text => { frames.push(text); }
  });
  if (frames.length > 1 || frames.some(frame => !frame.startsWith(gate.notice))) throw Error('host output custody failure');
  if (result.status === 'delivered' && (result.decisions.at(-1)?.decision !== 'allow' || !frames[0]?.includes('WARDEN_STRUCTURED_ANSWER\n'))) throw Error('unverified delivery');
  if (result.status !== 'delivered' && frames.some(frame => frame.includes('WARDEN_STRUCTURED_ANSWER\n'))) throw Error('candidate escaped withholding');
  return { ...slot, initialGrounding: c.initial_grounding, fixtureId: c.fixture.id, catalog: gate.catalog,
    initialAnswerSha256: c.initial_answer_sha256, proposals, result, frames };
}
