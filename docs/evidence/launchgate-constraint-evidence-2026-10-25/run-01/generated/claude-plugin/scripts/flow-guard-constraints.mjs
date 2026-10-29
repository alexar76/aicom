// GENERATED from src/flow-guard-constraints.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Optional host-supplied constraint evidence. No natural-language inference or permission grants. */
import { createHash } from 'node:crypto';
const object = (value) => !!value && typeof value === 'object' && !Array.isArray(value);
const exact = (value, keys) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const scalar = (value) => typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12;
const id = (value) => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/.test(value);
const field = (value) => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(value) && !['constructor', 'prototype'].includes(value);
const hash = (text) => createHash('sha256').update(text).digest('hex');
const same = (a, b) => typeof a === typeof b && a === b;
/** Fixed templates + finite scalars/positions only. No names, quotes, URLs or source-authored field labels. */
export function checkAnswerConstraints(value, answer, sessionId, turn) {
    const empty = (status) => ({ status, violations: [], unknownReferences: 0, text: status === 'invalid' ? 'WARDEN: constraint evidence is unavailable because the host check did not validate. This is not a passed check.' : '' });
    if (value === undefined)
        return empty('absent');
    if (!object(value) || !exact(value, ['schema', 'sessionId', 'turn', 'answerSha256', 'rules', 'records', 'claims']) || value.schema !== 'warden-answer-check/1' ||
        value.sessionId !== sessionId || !Number.isSafeInteger(value.turn) || value.turn < 1 || value.turn !== turn || value.answerSha256 !== hash(answer) ||
        !Array.isArray(value.rules) || !value.rules.length || value.rules.length > 16 || !Array.isArray(value.records) || !value.records.length || value.records.length > 256 || !object(value.claims))
        return empty('invalid');
    const rules = [];
    for (const candidate of value.rules) {
        if (!object(candidate) || !exact(candidate, ['field', 'op', 'value']) || !field(candidate.field) || typeof candidate.op !== 'string' || !['lte', 'gte', 'eq'].includes(candidate.op) || !scalar(candidate.value) || candidate.op !== 'eq' && typeof candidate.value !== 'number')
            return empty('invalid');
        rules.push(candidate);
    }
    const records = [];
    const seen = new Set();
    for (const candidate of value.records) {
        if (!object(candidate) || !exact(candidate, ['id', 'attributes']) || !id(candidate.id) || seen.has(candidate.id) || !object(candidate.attributes) || Object.keys(candidate.attributes).length > 32 ||
            !Object.entries(candidate.attributes).every(([key, entry]) => field(key) && scalar(entry)))
            return empty('invalid');
        records.push(candidate);
        seen.add(candidate.id);
    }
    const claims = value.claims;
    if (!exact(claims, ['selectedId', 'eligibleIds']) || !id(claims.selectedId) || !Array.isArray(claims.eligibleIds) || claims.eligibleIds.length > 128 || !claims.eligibleIds.every(id) || new Set(claims.eligibleIds).size !== claims.eligibleIds.length)
        return empty('invalid');
    // Stable facts identity is independent of selected claims and the generated answer.
    const factsSha256 = hash(JSON.stringify({ rules, records: records.map(record => ({ id: record.id, attributes: Object.fromEntries(Object.entries(record.attributes).sort(([a], [b]) => a.localeCompare(b))) })) }));
    const map = new Map(records.map(record => [record.id, record]));
    const referenced = [...new Set([claims.selectedId, ...claims.eligibleIds])];
    const violations = [];
    let unknownReferences = 0;
    for (const itemId of referenced) {
        const record = map.get(itemId);
        if (!record) {
            unknownReferences++;
            continue;
        }
        for (const [index, rule] of rules.entries()) {
            if (!Object.hasOwn(record.attributes, rule.field)) {
                unknownReferences++;
                continue;
            }
            const actual = record.attributes[rule.field];
            if (rule.op !== 'eq' && typeof actual !== 'number') {
                unknownReferences++;
                continue;
            }
            const passes = rule.op === 'eq' ? same(actual, rule.value) : rule.op === 'lte' ? actual <= rule.value : actual >= rule.value;
            if (!passes)
                violations.push({ item: records.indexOf(record) + 1, rule: index + 1, op: rule.op, limit: rule.value, actual });
        }
    }
    const snippets = violations.slice(0, 8).map(v => `Claimed eligible item #${v.item} violates rule #${v.rule}: actual ${v.actual}; required ${v.op === 'lte' ? '<=' : v.op === 'gte' ? '>=' : '==='} ${v.limit}.`);
    const status = unknownReferences ? 'partial' : 'checked';
    const text = snippets.length ? 'WARDEN constraint evidence (conditional on the host record snapshot): ' + snippets.join(' ') + (violations.length > 8 ? ` ${violations.length - 8} more contradictions recorded.` : '') + (unknownReferences ? ' Some references or fields are unknown; this is not a complete check.' : '') : unknownReferences ? 'WARDEN: some claimed items or rule fields are unknown. Constraint checking is incomplete, not passed.' : '';
    return { status, factsSha256, violations, unknownReferences, text };
}
