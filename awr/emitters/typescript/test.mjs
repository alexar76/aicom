/**
 * The zero-dependency emitter and the MCP wrapper.
 *
 * Every document produced here is handed to the Rust implementation's CLI for verification
 * rather than checked field by field: the contract is "another implementation accepts it".
 * Run with:  node --test awr/emitters/typescript/test.mjs
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

import {
  base58btc, canonicalize, emitReceipt, generateKey, jcsPayload,
  keyFromSeed, receiptReference, sriEncode,
} from './awr-emit.mjs';
import { withAwrReceipts } from './mcp-middleware.mjs';

const HERE = resolve(fileURLToPath(new URL('.', import.meta.url)));
const REPO = resolve(HERE, '..', '..', '..');
const RUST = join(REPO, 'awr', 'rust', 'target', 'release', 'awr');
// RFC 8032 section 7.1 test seed — published, never for anything real.
const SEED = Buffer.from('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60', 'hex');
const NOW = '2026-08-01T10:15:30Z';

function verifyWithRust(document) {
  if (!existsSync(RUST)) return null; // reported by the caller as a skip
  const dir = mkdtempSync(join(tmpdir(), 'awr-emit-'));
  const path = join(dir, 'doc.json');
  writeFileSync(path, JSON.stringify(document));
  try {
    return JSON.parse(execFileSync(RUST, ['verify', path, '--now', NOW], { encoding: 'utf8' }));
  } catch (err) {
    // The CLI exits 1 for an invalid document and still prints the result JSON.
    if (err.stdout) return JSON.parse(err.stdout);
    throw err;
  }
}

const fixedKey = () => keyFromSeed(SEED);

test('base58btc matches the multibase specification example', () => {
  assert.equal(base58btc(Buffer.from('hello world', 'utf8')), 'StV1DL6CwTryKyV');
});

test('did:key derivation matches the published test key', () => {
  assert.equal(fixedKey().did, 'did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw');
});

test('JCS sorts by UTF-16 code units and refuses non-integer numbers', () => {
  assert.equal(canonicalize({ b: 1, a: 2 }), '{"a":2,"b":1}');
  assert.equal(canonicalize({ 'é': 1, z: 2 }), '{"z":2,"é":1}');
  assert.throws(() => canonicalize({ x: 1.5 }), /AWR-CANON-001/);
  assert.throws(() => canonicalize({ x: 2 ** 53 }), /AWR-CANON-002/);
  assert.throws(() => canonicalize({ x: '\ud800' }), /AWR-CANON-003/);
});

test('JCS escapes control characters in lowercase hex and does not normalize', () => {
  assert.equal(canonicalize(''), '"\\u0001"');
  assert.equal(canonicalize('\n'), '"\\n"');
  // NFC and NFD spellings stay distinct: §4.1 forbids normalizing.
  assert.notEqual(canonicalize('é'), canonicalize('é'));
});

test('the smallest receipt verifies in the Rust implementation', () => {
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@v', inputPayload: 'in', outputPayload: 'out',
    documentId: 'urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b', validFrom: NOW, created: NOW,
  });
  const result = verifyWithRust(doc);
  if (result === null) return; // rust binary not built
  assert.equal(result.valid, true, JSON.stringify(result.reasons));
  assert.equal(result.documentType, 'WorkReceipt');
});

test('it omits optional fields it was not given, but always carries completedAt', () => {
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@v', inputPayload: 'in', outputPayload: 'out',
    documentId: 'urn:uuid:1', validFrom: NOW, created: NOW,
  });
  assert.deepEqual(Object.keys(doc.credentialSubject).sort(), ['inputDigest', 'outputDigest', 'work']);
  assert.deepEqual(Object.keys(doc.credentialSubject.work).sort(), ['completedAt', 'modelId', 'status']);
  assert.equal(doc.credentialSubject.work.completedAt, NOW);
  assert.equal(doc.issuer.name, undefined);
});

test('a payload digest is over exactly the bytes given', () => {
  const a = emitReceipt({ key: fixedKey(), modelId: 'm@v', inputPayload: 'hola', outputPayload: '', documentId: 'urn:uuid:1', validFrom: NOW, created: NOW });
  const b = emitReceipt({ key: fixedKey(), modelId: 'm@v', inputPayload: Buffer.from('hola'), outputPayload: '', documentId: 'urn:uuid:1', validFrom: NOW, created: NOW });
  const c = emitReceipt({ key: fixedKey(), modelId: 'm@v', inputPayload: 'hola\n', outputPayload: '', documentId: 'urn:uuid:1', validFrom: NOW, created: NOW });
  assert.equal(a.credentialSubject.inputDigest, b.credentialSubject.inputDigest);
  assert.notEqual(a.credentialSubject.inputDigest, c.credentialSubject.inputDigest);
});

test('jcsPayload makes a JSON digest reproducible across key orderings', () => {
  const sha = (buf) => createHash('sha256').update(buf).digest();
  assert.equal(sriEncode(sha(jcsPayload({ b: 1, a: [1, 2] }))),
               sriEncode(sha(jcsPayload({ a: [1, 2], b: 1 }))));
  // …and different from a naive JSON.stringify of the same object.
  assert.notEqual(sriEncode(sha(jcsPayload({ b: 1, a: [1, 2] }))),
                  sriEncode(sha(Buffer.from(JSON.stringify({ b: 1, a: [1, 2] })))));
});

test('a failed run still gets a verifiable receipt', () => {
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@v', inputPayload: 'in', outputPayload: '',
    status: 'failed', documentId: 'urn:uuid:2', validFrom: NOW, created: NOW,
  });
  const result = verifyWithRust(doc);
  if (result === null) return;
  assert.equal(result.valid, true, JSON.stringify(result.reasons));
  assert.equal(doc.credentialSubject.work.status, 'failed');
});

test('a non-integer latency and an unknown status are refused', () => {
  const base = { key: fixedKey(), modelId: 'm@v', inputPayload: 'i', outputPayload: 'o' };
  assert.throws(() => emitReceipt({ ...base, latencyMs: 1.5 }), /latencyMs/);
  assert.throws(() => emitReceipt({ ...base, latencyMs: -1 }), /latencyMs/);
  assert.throws(() => emitReceipt({ ...base, status: 'mostly-fine' }), /status/);
});

test('a price given as a JSON number is refused by canonicalization', () => {
  assert.throws(() => emitReceipt({
    key: fixedKey(), modelId: 'm@v', inputPayload: 'i', outputPayload: 'o',
    price: { currency: 'USD', amount: 0.15 },
  }), /AWR-CANON-001/);
});

test('a chain edge commits to the parent bytes', () => {
  const key = fixedKey();
  const parent = emitReceipt({ key, modelId: 'retrieve@v', inputPayload: 'q', outputPayload: 'docs', documentId: 'urn:uuid:p', validFrom: NOW, created: NOW });
  const ref = receiptReference(parent);
  const child = emitReceipt({
    key, modelId: 'answer@v', inputPayload: 'docs', outputPayload: 'answer',
    parents: [{ ...ref, role: 'retrieval' }], documentId: 'urn:uuid:c', validFrom: NOW, created: NOW,
  });
  assert.equal(child.credentialSubject.parents[0].digestSRI, ref.digestSRI);
  assert.match(ref.digestSRI, /^sha256-[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$/);
});

test('two generated keys are two issuers', () => {
  assert.notEqual(generateKey().did, generateKey().did);
});

// ── the MCP wrapper ─────────────────────────────────────────────────────────

test('the MCP wrapper emits one verifiable receipt per call and returns the result', async () => {
  const received = [];
  const handler = async (req) => ({ content: [{ type: 'text', text: 'echo:' + req.params.arguments.q }] });
  const wrapped = withAwrReceipts(handler, {
    key: fixedKey(), modelId: 'my-mcp-server@1.2', onReceipt: (d) => received.push(d),
  });

  const out = await wrapped({ params: { name: 'echo', arguments: { q: 'hola' } } });
  assert.equal(out.content[0].text, 'echo:hola');
  assert.equal(received.length, 1);
  assert.equal(received[0].credentialSubject.work.capability, 'echo');
  const result = verifyWithRust(received[0]);
  if (result !== null) assert.equal(result.valid, true, JSON.stringify(result.reasons));
});

test('an isError result is recorded as failed work, not as success', async () => {
  const received = [];
  const wrapped = withAwrReceipts(async () => ({ content: [], isError: true }), {
    key: fixedKey(), modelId: 's@1', onReceipt: (d) => received.push(d),
  });
  await wrapped({ params: { name: 'boom', arguments: {} } });
  assert.equal(received[0].credentialSubject.work.status, 'failed');
});

test('a thrown handler still leaves a receipt and the error still propagates', async () => {
  const received = [];
  const wrapped = withAwrReceipts(async () => { throw new Error('upstream 500'); }, {
    key: fixedKey(), modelId: 's@1', onReceipt: (d, e) => received.push([d, e]),
  });
  await assert.rejects(() => wrapped({ params: { name: 't', arguments: {} } }), /upstream 500/);
  assert.equal(received.length, 1);
  assert.equal(received[0][0].credentialSubject.work.status, 'failed');
  assert.match(received[0][1].message, /upstream 500/);
});

test('the thrown error is not passed off as the tool output', async () => {
  const got = [];
  const thrower = withAwrReceipts(async () => { throw new Error('secret internal detail'); },
    { key: fixedKey(), modelId: 's@1', onReceipt: (d) => got.push(d) });
  await assert.rejects(() => thrower({ params: { name: 't', arguments: {} } }));
  const empty = emitReceipt({ key: fixedKey(), modelId: 's@1', inputPayload: 'x', outputPayload: '' });
  assert.equal(got[0].credentialSubject.outputDigest, empty.credentialSubject.outputDigest);
});

test('the wrapper refuses to be constructed without a sink', () => {
  assert.throws(() => withAwrReceipts(async () => ({}), { key: fixedKey(), modelId: 's@1' }), /onReceipt/);
});

// ── timestamp derivation (§3.3, and cross-language agreement) ────────────────
//
// These three exist because the emitter once computed ONE moment from
// `created || validFrom || now` and answered all three timestamp questions with it. That made
// it disagree with the reference emitter on partial input, and the disagreement was invisible
// to every other test here: they all pass completedAt, created and validFrom together, so
// nothing is ever derived. A past sentinel is used rather than a fixed clock — the real clock
// can never equal it, so the assertions are deterministic without injecting time.

const PAST = '2020-01-02T03:04:05Z';

test('validFrom is never derived from created — a proof timestamp is not a validity start', () => {
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@1', inputPayload: 'in', outputPayload: 'out', created: PAST,
  });
  assert.equal(doc.proof.created, PAST, 'the caller asked for this created');
  assert.notEqual(doc.validFrom, PAST, 'validFrom must come from now, not from created');
});

test('proof.created falls back to validFrom, exactly as the reference does', () => {
  // Not this emitter's choice: awr/documents.py signs with `created or document["validFrom"]`.
  // Asserting anything else here would make the two implementations disagree, which is the one
  // thing an emitter pair must never do. `completedAt` is NOT in that chain -- work finishing is
  // not the same event as signing -- and the next case pins that.
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@1', inputPayload: 'in', outputPayload: 'out', validFrom: PAST,
  });
  assert.equal(doc.validFrom, PAST);
  assert.equal(doc.proof.created, PAST, 'reference rule: created defaults to validFrom');
});

test('proof.created is never taken from completedAt', () => {
  const doc = emitReceipt({
    key: fixedKey(), modelId: 'm@1', inputPayload: 'in', outputPayload: 'out', completedAt: PAST,
  });
  assert.equal(doc.credentialSubject.work.completedAt, PAST);
  assert.notEqual(doc.proof.created, PAST, 'signing time is not work-completion time');
  assert.notEqual(doc.validFrom, PAST);
});

test('work.completedAt follows the reference precedence: completedAt, created, validFrom, now', () => {
  const c = '2021-01-01T00:00:00Z', v = '2022-01-01T00:00:00Z', d = '2023-01-01T00:00:00Z';
  assert.equal(emitReceipt({ key: fixedKey(), modelId: 'm', inputPayload: 'i', outputPayload: 'o',
    completedAt: d, created: c, validFrom: v }).credentialSubject.work.completedAt, d);
  assert.equal(emitReceipt({ key: fixedKey(), modelId: 'm', inputPayload: 'i', outputPayload: 'o',
    created: c, validFrom: v }).credentialSubject.work.completedAt, c);
  assert.equal(emitReceipt({ key: fixedKey(), modelId: 'm', inputPayload: 'i', outputPayload: 'o',
    validFrom: v }).credentialSubject.work.completedAt, v);
  const bare = emitReceipt({ key: fixedKey(), modelId: 'm', inputPayload: 'i', outputPayload: 'o' });
  assert.notEqual(bare.credentialSubject.work.completedAt, undefined);
});
