/** Host-owned structured answer validation and bounded correction. No model client or network calls. */
import { createHash } from 'node:crypto';
import { parseJsonStrict } from './jcs.js';
const object = (v) => !!v && typeof v === 'object' && !Array.isArray(v) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(v)) && Object.values(Object.getOwnPropertyDescriptors(v)).every(d => 'value' in d);
const exact = (v, names) => Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k));
const scalar = (v) => typeof v === 'boolean' || typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 1e12;
const field = (v) => typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(v) && !['constructor', 'prototype'].includes(v);
const hash = (v) => createHash('sha256').update(v).digest('hex');
const refPattern = /^rec-[0-9a-f]{24}$/;
const scalarText = (v) => JSON.stringify(v);
function freeze(value) {
    if (value && typeof value === 'object') {
        for (const child of Object.values(value))
            freeze(child);
        Object.freeze(value);
    }
    return value;
}
function passes(actual, rule) {
    return rule.op === 'eq' ? typeof actual === typeof rule.value && actual === rule.value
        : typeof actual === 'number' && (rule.op === 'lte' ? actual <= rule.value : actual >= rule.value);
}
/** Only string fields and string arrays are valid proposals; use the existing duplicate-key rejecting parser. */
function parseCandidate(raw) {
    if (typeof raw !== 'string' || raw.length > 32_768)
        throw new Error('invalid JSON');
    return parseJsonStrict(raw);
}
/**
 * The host owns rules, snapshot, context and output. Raw model prose is deliberately unsupported.
 * Safe aliases replace source IDs/field labels in both the model catalog and every counterexample.
 */
export function createAnswerGate(options) {
    const fail = () => { throw new TypeError('Invalid answer gate contract'); };
    if (!object(options))
        return fail();
    const allowed = ['sessionId', 'turn', 'rules', 'records', 'ranking', 'disclosure'];
    if (Object.keys(options).some(k => !allowed.includes(k)) || typeof options.sessionId !== 'string' || !options.sessionId.trim() || options.sessionId.length > 200 ||
        !Number.isSafeInteger(options.turn) || options.turn < 1 || !Array.isArray(options.rules) || !options.rules.length || options.rules.length > 16 ||
        !Array.isArray(options.records) || options.records.length > 256 || options.disclosure !== undefined && !['external-data', 'source-instructions'].includes(options.disclosure))
        return fail();
    const rules = options.rules.map(r => {
        if (!object(r) || !exact(r, ['field', 'op', 'value']) || !field(r.field) || !['lte', 'gte', 'eq'].includes(r.op) ||
            !scalar(r.value) || r.op !== 'eq' && typeof r.value !== 'number')
            return fail();
        return { field: r.field, op: r.op, value: r.value };
    });
    let ranking;
    if (options.ranking !== undefined) {
        const r = options.ranking;
        if (!object(r) || !exact(r, ['field', 'direction']) || !field(r.field) || !['min', 'max'].includes(r.direction))
            return fail();
        ranking = { field: r.field, direction: r.direction };
    }
    const fields = [...new Set([...rules.map(r => r.field), ...(ranking ? [ranking.field] : [])])];
    const handles = new Map(fields.map((name, i) => [name, `field_${i + 1}`]));
    const seen = new Set();
    const refs = new Set();
    const sourceRefs = new Map();
    let incomplete = false;
    const records = options.records.map(record => {
        if (!object(record) || !exact(record, ['id', 'attributes']) || typeof record.id !== 'string' || !record.id.length || record.id.length > 256 || seen.has(record.id) ||
            !object(record.attributes) || Object.keys(record.attributes).length > 32 || !Object.entries(record.attributes).every(([k, v]) => field(k) && scalar(v)))
            return fail();
        seen.add(record.id);
        const ref = 'rec-' + hash(JSON.stringify([options.sessionId, options.turn, record.id])).slice(0, 24);
        if (refs.has(ref))
            return fail();
        refs.add(ref);
        sourceRefs.set(record.id, ref);
        const attributes = {};
        for (const key of fields) {
            if (!Object.hasOwn(record.attributes, key)) {
                incomplete = true;
                continue;
            }
            attributes[handles.get(key)] = record.attributes[key];
        }
        if (ranking && typeof record.attributes[ranking.field] !== 'number')
            incomplete = true;
        // Ordered comparisons on boolean data are not verified by numeric coercion.
        for (const rule of rules)
            if (rule.op !== 'eq' && typeof record.attributes[rule.field] !== 'number')
                incomplete = true;
        return { ref, attributes };
    }).sort((a, b) => a.ref.localeCompare(b.ref));
    const publicRules = rules.map(r => ({ ...r, field: handles.get(r.field) }));
    const publicRanking = ranking ? { ...ranking, field: handles.get(ranking.field) } : undefined;
    const digest = hash(JSON.stringify({ sessionId: options.sessionId, turn: options.turn, rules: publicRules, records, ranking: publicRanking ?? null }));
    const catalog = freeze({ schema: 'warden-answer-catalog/1', catalogSha256: digest, rules: publicRules, records,
        ...(publicRanking ? { ranking: publicRanking } : {}), responseSchema: 'warden-selection/1' });
    const notice = options.disclosure === 'source-instructions'
        ? 'WARDEN: The external source contained text addressed to the assistant as instructions. This notice is owned by the host, independently of the model answer. Structured checks do not prove that those instructions were rejected or that source facts are true.'
        : 'WARDEN: This result uses external records. Only the declared structured constraints are checked; source truth and arbitrary natural-language claims are not verified.';
    const map = new Map(records.map(r => [r.ref, r]));
    const eligible = incomplete ? [] : records.filter(r => publicRules.every(rule => passes(r.attributes[rule.field], rule))).map(r => r.ref);
    let optimal = [...eligible];
    if (!incomplete && publicRanking && eligible.length) {
        const values = eligible.map(ref => map.get(ref).attributes[publicRanking.field]);
        const best = publicRanking.direction === 'min' ? Math.min(...values) : Math.max(...values);
        optimal = eligible.filter(ref => map.get(ref).attributes[publicRanking.field] === best);
    }
    function decision(raw, kind, code, violations = [], answer) {
        const details = violations.slice(0, 16).map(v => `Record ${v.recordRef}, ${v.field}: actual ${scalarText(v.actual)}; required ${v.op === 'lte' ? '<=' : v.op === 'gte' ? '>=' : '==='} ${scalarText(v.required)}.`).join(' ');
        const feedback = code === 'verified' ? 'WARDEN: all declared structured checks passed against this frozen snapshot.'
            : `WARDEN structured answer check: ${code}. ${details}${violations.length > 16 ? ` ${violations.length - 16} further violations recorded.` : ''} Recompute the complete eligible set from every declared rule and the frozen catalog. Preserve the host-owned disclosure. Return only the declared structured schema; do not add prose.`;
        return freeze({ decision: kind, code, answerSha256: hash(typeof raw === 'string' ? raw : ''), feedback, violations, ...(answer ? { answer } : {}) });
    }
    function evaluate(raw) {
        if (incomplete)
            return decision(raw, 'unknown', 'incomplete-facts');
        if (!eligible.length)
            return decision(raw, 'deny', 'no-eligible-records');
        let value;
        try {
            value = parseCandidate(raw);
        }
        catch {
            return decision(raw, 'unknown', 'invalid-json');
        }
        if (!object(value) || !exact(value, ['schema', 'catalogSha256', 'selectedRef', 'eligibleRefs']) || value.schema !== 'warden-selection/1' ||
            typeof value.catalogSha256 !== 'string' || typeof value.selectedRef !== 'string' || !refPattern.test(value.selectedRef) || !Array.isArray(value.eligibleRefs) ||
            value.eligibleRefs.length > 256 || !value.eligibleRefs.every(r => typeof r === 'string' && refPattern.test(r)) || new Set(value.eligibleRefs).size !== value.eligibleRefs.length)
            return decision(raw, 'unknown', 'invalid-schema');
        if (value.catalogSha256 !== digest)
            return decision(raw, 'unknown', 'stale-catalog');
        const selected = value.selectedRef;
        const claimed = value.eligibleRefs;
        if (![selected, ...claimed].every(ref => map.has(ref)))
            return decision(raw, 'unknown', 'unknown-record');
        const violations = [];
        for (const ref of new Set([selected, ...claimed])) {
            const record = map.get(ref);
            for (const rule of publicRules)
                if (!passes(record.attributes[rule.field], rule))
                    violations.push({ recordRef: ref, field: rule.field, op: rule.op, actual: record.attributes[rule.field], required: rule.value });
        }
        if (violations.length)
            return decision(raw, 'deny', 'constraint-violation', violations);
        // Complete eligible sets prevent a model from silently dropping inconvenient alternatives.
        if (claimed.length !== eligible.length || !eligible.every(ref => claimed.includes(ref)))
            return decision(raw, 'deny', 'incomplete-eligible-set');
        if (!optimal.includes(selected))
            return decision(raw, 'deny', 'not-optimal');
        return decision(raw, 'allow', 'verified', [], { schema: 'warden-selection/1', catalogSha256: digest, selectedRef: selected, eligibleRefs: [...eligible] });
    }
    let used = false;
    async function run(runOptions) {
        if (used)
            throw new Error('Answer gate output reservation already used');
        const corrections = runOptions.maxCorrections ?? 2;
        const timeout = runOptions.timeoutMs ?? 30_000;
        if (![0, 1, 2].includes(corrections) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 120_000 || typeof runOptions.generate !== 'function' || typeof runOptions.emit !== 'function')
            throw new TypeError('Invalid answer gate run options');
        used = true;
        const decisions = [];
        let attempts = 0;
        const finish = async (status, result) => {
            const output = result?.decision === 'allow'
                ? `${notice}\nWARDEN_STRUCTURED_ANSWER\n${JSON.stringify({ ...result.answer, records: records.filter(r => result.answer.eligibleRefs.includes(r.ref)) })}\n`
                : `${notice}\nWARDEN_RESULT_WITHHELD: ${result?.code ?? status}. No unverified candidate was forwarded.\n`;
            if (runOptions.signal?.aborted)
                return freeze({ status: 'cancelled', attempts, decisions: [...decisions], ...(result ? { lastCode: result.code } : {}) });
            try {
                await runOptions.emit(output);
            }
            catch {
                return freeze({ status: 'delivery-uncertain', attempts, decisions: [...decisions], ...(result ? { lastCode: result.code } : {}) });
            }
            if (runOptions.signal?.aborted)
                return freeze({ status: 'delivery-uncertain', attempts, decisions: [...decisions], ...(result ? { lastCode: result.code } : {}) });
            return freeze({ status, attempts, decisions: [...decisions], ...(result ? { lastCode: result.code } : {}) });
        };
        if (runOptions.signal?.aborted)
            return freeze({ status: 'cancelled', attempts, decisions: [] });
        if (incomplete || !eligible.length)
            return finish('withheld', evaluate(''));
        for (let attempt = 0; attempt <= corrections; attempt++) {
            if (runOptions.signal?.aborted)
                return freeze({ status: 'cancelled', attempts, decisions: [...decisions] });
            const controller = new AbortController();
            const abort = () => controller.abort();
            runOptions.signal?.addEventListener('abort', abort, { once: true });
            let timer;
            let remove;
            attempts++;
            let raw;
            try {
                raw = await new Promise((resolve, reject) => {
                    const cancelled = () => reject(new Error('generation aborted'));
                    controller.signal.addEventListener('abort', cancelled, { once: true });
                    remove = () => controller.signal.removeEventListener('abort', cancelled);
                    timer = setTimeout(() => controller.abort(), timeout);
                    Promise.resolve().then(() => {
                        if (controller.signal.aborted)
                            throw new Error('generation aborted');
                        return runOptions.generate(Object.freeze({ attempt, catalog, ...(decisions.length ? { feedback: decisions[decisions.length - 1].feedback } : {}), signal: controller.signal }));
                    }).then(resolve, reject);
                });
            }
            catch {
                if (runOptions.signal?.aborted)
                    return freeze({ status: 'cancelled', attempts, decisions: [...decisions] });
                return finish('generation-error', decisions[decisions.length - 1]);
            }
            finally {
                if (timer !== undefined)
                    clearTimeout(timer);
                remove?.();
                runOptions.signal?.removeEventListener('abort', abort);
            }
            if (runOptions.signal?.aborted)
                return freeze({ status: 'cancelled', attempts, decisions: [...decisions] });
            const result = evaluate(raw);
            decisions.push(result);
            if (result.decision === 'allow')
                return finish('delivered', result);
        }
        return finish('withheld', decisions[decisions.length - 1]);
    }
    return Object.freeze({ catalog, notice, referenceForRecord: (sourceId) => sourceRefs.get(sourceId), evaluate, run });
}
//# sourceMappingURL=answer-gate.js.map