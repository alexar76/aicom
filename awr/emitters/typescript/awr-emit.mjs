/**
 * Emit an AWR/2 WorkReceipt from Node with ZERO runtime dependencies.
 *
 * Node 22 has Ed25519 and SHA-256 in `node:crypto`, so the only things this file has to
 * carry are the format's own rules: RFC 8785 canonicalization (SPEC.md §4), base58btc and
 * multibase, `did:key` derivation (§5) and the `eddsa-jcs-2022` proof (§6). It is written
 * out here rather than imported because the point of a zero-dependency emitter is that
 * `npm install` is not a step — an adopter copies one file.
 *
 * It MUST produce byte-identical documents to awr/emitters/python for the same inputs and
 * key; `test.mjs` proves it against a document the Python emitter issued.
 *
 * WHAT GETS DIGESTED: the same rule as the Python emitter — exactly the bytes you pass. A
 * string is encoded UTF-8 with no normalization. For a JSON payload whose digest a third
 * party must be able to reproduce, pass it through `jcsPayload(obj)` first.
 */

import { createHash, createPrivateKey, createPublicKey, sign as cryptoSign, generateKeyPairSync } from 'node:crypto';

export const VC_CONTEXT = 'https://www.w3.org/ns/credentials/v2';
export const AWR_CONTEXT = 'https://verify.modelmarket.dev/ns/awr/v2';
export const AWR_VERSION = '2.0.0';
export const CRYPTOSUITE = 'eddsa-jcs-2022';
const WORK_STATUSES = ['succeeded', 'failed', 'refused', 'timeout', 'partial'];
const MAX_SAFE = 9007199254740991;

// ── RFC 8785 (JCS), as profiled by SPEC.md §4 ───────────────────────────────

const ESCAPES = { 0x08: '\\b', 0x09: '\\t', 0x0a: '\\n', 0x0c: '\\f', 0x0d: '\\r', 0x22: '\\"', 0x5c: '\\\\' };

function jcsString(s) {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const cp = s.charCodeAt(i);
    // Lone surrogates are not valid Unicode and §4.1 requires an error, not a
    // replacement character: substituting one would change the bytes that get signed.
    if (cp >= 0xd800 && cp <= 0xdbff) {
      const next = s.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error('AWR-CANON-003: lone high surrogate');
      out += s[i] + s[i + 1]; i++; continue;
    }
    if (cp >= 0xdc00 && cp <= 0xdfff) throw new Error('AWR-CANON-003: lone low surrogate');
    if (ESCAPES[cp]) { out += ESCAPES[cp]; continue; }
    if (cp < 0x20) { out += '\\u' + cp.toString(16).padStart(4, '0'); continue; } // lowercase hex
    out += s[i];
  }
  return out + '"';
}

/** §4: canonical JSON. §4.3: integers only — a non-integer number is a hard error. */
export function canonicalize(value) {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('AWR-CANON-001: NaN/Infinity is not JSON');
    if (!Number.isInteger(value)) throw new Error('AWR-CANON-001: non-integer number ' + value);
    if (Math.abs(value) > MAX_SAFE) throw new Error('AWR-CANON-002: integer out of range ' + value);
    return String(value);
  }
  if (typeof value === 'string') return jcsString(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalize).join(',') + ']';
  if (typeof value === 'object') {
    // §4.1 rule 1: sort by UTF-16 code units. JavaScript's default string comparison IS
    // code-unit order, which is the one rule the platform gives away for free —
    // localeCompare is NOT this and must never be used here.
    const keys = Object.keys(value).sort();
    return '{' + keys.map((k) => jcsString(k) + ':' + canonicalize(value[k])).join(',') + '}';
  }
  throw new Error('AWR-CANON-005: value of unsupported type ' + typeof value);
}

export function jcsPayload(value) { return Buffer.from(canonicalize(value), 'utf8'); }

// ── digests, base58btc, multibase, did:key ──────────────────────────────────

const sha256 = (buf) => createHash('sha256').update(buf).digest();

/** §3.2: `sha256-` + canonical padded base64. Node's base64 is already canonical. */
export function sriEncode(digest) { return 'sha256-' + digest.toString('base64'); }

const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

export function base58btc(bytes) {
  let zeros = 0;
  while (zeros < bytes.length && bytes[zeros] === 0) zeros++;
  const digits = [0];
  for (let i = zeros; i < bytes.length; i++) {
    let carry = bytes[i];
    for (let j = 0; j < digits.length; j++) {
      carry += digits[j] << 8;
      digits[j] = carry % 58;
      carry = (carry / 58) | 0;
    }
    while (carry) { digits.push(carry % 58); carry = (carry / 58) | 0; }
  }
  let out = '1'.repeat(zeros);
  for (let i = digits.length - 1; i >= 0; i--) out += B58[digits[i]];
  return out;
}

/** §5.1: did:key = "did:key:z" + base58btc(0xed 0x01 || 32-byte public key). */
export function didKeyFromPublicKey(publicKeyBytes) {
  if (publicKeyBytes.length !== 32) throw new Error('AWR-KEY-002: Ed25519 public key must be 32 bytes');
  return 'did:key:z' + base58btc(Buffer.concat([Buffer.from([0xed, 0x01]), publicKeyBytes]));
}

// ── keys ────────────────────────────────────────────────────────────────────

const PKCS8_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex');
const SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');

/** A signing key from a 32-byte seed (the RFC 8032 private key). */
export function keyFromSeed(seed) {
  if (seed.length !== 32) throw new Error('Ed25519 seed must be 32 bytes');
  const privateKey = createPrivateKey({ key: Buffer.concat([PKCS8_PREFIX, seed]), format: 'der', type: 'pkcs8' });
  const publicKey = createPublicKey(privateKey);
  const raw = publicKey.export({ format: 'der', type: 'spki' }).subarray(SPKI_PREFIX.length);
  return { privateKey, publicKeyBytes: raw, did: didKeyFromPublicKey(raw) };
}

export function generateKey() {
  const { privateKey } = generateKeyPairSync('ed25519');
  const raw = createPublicKey(privateKey).export({ format: 'der', type: 'spki' }).subarray(SPKI_PREFIX.length);
  return { privateKey, publicKeyBytes: raw, did: didKeyFromPublicKey(raw) };
}

// ── the proof (§6.2) ────────────────────────────────────────────────────────

function signDocument(unsecured, key, created) {
  const verificationMethod = key.did + '#' + key.did.slice('did:key:'.length);
  // §6.2 step 1: the proof config carries the document's @context, and §6 requires it to
  // be EMITTED too — a W3C VC library recomputes the config from the proof verbatim, and
  // omitting it is what made an off-the-shelf verifier report "Invalid signature" against
  // a signature that was in fact correct.
  const options = {
    '@context': unsecured['@context'],
    type: 'DataIntegrityProof',
    cryptosuite: CRYPTOSUITE,
    created,
    verificationMethod,
    proofPurpose: 'assertionMethod',
  };
  const proofConfigHash = sha256(Buffer.from(canonicalize(options), 'utf8'));
  const documentHash = sha256(Buffer.from(canonicalize(unsecured), 'utf8'));
  // §6.2 step 6: proof config FIRST. Swapping these is the most common Data Integrity bug.
  const signature = cryptoSign(null, Buffer.concat([proofConfigHash, documentHash]), key.privateKey);
  return { ...options, proofValue: 'z' + base58btc(signature) };
}

// ── the emitter ─────────────────────────────────────────────────────────────

function digestOf(payload) {
  if (typeof payload === 'string') return sriEncode(sha256(Buffer.from(payload, 'utf8')));
  if (Buffer.isBuffer(payload) || payload instanceof Uint8Array) return sriEncode(sha256(Buffer.from(payload)));
  throw new TypeError('payload must be a Buffer/Uint8Array or string; for JSON call jcsPayload(obj)');
}

export function emitReceipt(opts) {
  const {
    key, modelId, inputPayload, outputPayload,
    status = 'succeeded', capability, startedAt, completedAt, latencyMs,
    price, nonce, parents, issuerName,
    documentId, validFrom, created,
  } = opts;

  if (!WORK_STATUSES.includes(status)) throw new Error('status must be one of ' + WORK_STATUSES.join(', '));
  if (latencyMs !== undefined && (!Number.isInteger(latencyMs) || latencyMs < 0)) {
    throw new Error('latencyMs must be a non-negative integer (§3.3)');
  }

  // One clock reading per call, and THREE separate questions answered from it. An earlier
  // version computed a single `moment = created || validFrom || now` and used it for all three,
  // which made this emitter disagree with the reference: given only `created`, it set
  // `validFrom` to the caller's proof timestamp, and given only `validFrom` it set
  // `proof.created` to the validity start — that second one is a false statement about when the
  // signature was made. Found by emitting the same partial input from both languages and
  // diffing the bytes; the pre-existing cross-language test could not see it because it supplies
  // completedAt, created and validFrom together, so nothing was ever derived.
  const nowStamp = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const work = { modelId, status };
  if (capability !== undefined) work.capability = capability;
  if (startedAt !== undefined) work.startedAt = startedAt;
  // §3.3 REQUIRES work.completedAt, so it is always carried. The fallback chain mirrors the
  // reference emitter's exactly (completedAt -> created -> validFrom -> now): a caller who
  // stamped the document at one moment did the work at that moment unless they say otherwise.
  work.completedAt = completedAt || created || validFrom || nowStamp;
  if (latencyMs !== undefined) work.latencyMs = latencyMs;

  const credentialSubject = {
    work,
    inputDigest: digestOf(inputPayload),
    outputDigest: digestOf(outputPayload),
  };
  if (parents && parents.length) credentialSubject.parents = parents;
  if (price !== undefined) credentialSubject.price = price;
  if (nonce !== undefined) credentialSubject.nonce = nonce;

  const issuer = { id: key.did };
  if (issuerName !== undefined) issuer.name = issuerName;

  // Key insertion order mirrors the reference emitter so the pretty-printed JSON matches
  // too. JCS sorts keys, so the SIGNATURE never depends on this — only the file does.
  const unsecured = {
    '@context': [VC_CONTEXT, AWR_CONTEXT],
    id: documentId || 'urn:uuid:' + crypto.randomUUID(),
    type: ['VerifiableCredential', 'WorkReceipt'],
    issuer,
    // Validity start: the caller's, else now. Never `created` — a proof timestamp says when the
    // signature was made, not when the credential becomes valid.
    validFrom: validFrom || nowStamp,
    awrVersion: AWR_VERSION,
    credentialSubject,
  };
  // proof.created: the caller's, else the document's own validFrom. Not a free choice — it is
  // what the reference does (`awr/documents.py`: `created or document["validFrom"]`), and for a
  // freshly issued document validFrom IS the issuance moment, so the two agree without taking a
  // second clock reading that could drift. Never `completedAt`: work finishing is not signing.
  return { ...unsecured, proof: signDocument(unsecured, key, created || unsecured.validFrom) };
}

/** §8.1: a `{id, digestSRI}` edge committing to the parent's exact secured bytes. */
export function receiptReference(document) {
  return { id: document.id, digestSRI: sriEncode(sha256(Buffer.from(canonicalize(document), 'utf8'))) };
}
