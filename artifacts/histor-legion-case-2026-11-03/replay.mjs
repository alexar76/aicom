import assert from 'node:assert/strict';
import { createHash, createPublicKey, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';

const read = (file) => JSON.parse(readFileSync(new URL(file, import.meta.url), 'utf8'));
const histor = read('histor.json');
const record = read('legion.json').doc.latest_record;

// JCS for the JSON values in these fixtures. Object keys are ordered by UTF-16
// code units. String and number serialization uses ECMAScript JSON.stringify.
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    const members = Object.keys(value).sort().map(
      (key) => JSON.stringify(key) + ':' + canonical(value[key]),
    );
    return '{' + members.join(',') + '}';
  }
  return JSON.stringify(value);
}

const rootPin = 'a7c6a35b1c2c81d589a30c2ad628679bdea9da4139d49aa3c42cdde6e1c65036';
const hash = (...parts) => {
  const digest = createHash('sha256');
  for (const part of parts) digest.update(part);
  return digest.digest();
};
const pin = (key) => hash(key).toString('hex');

function checkSignature(key, signature, message) {
  assert.equal(key.length, 32);
  const spki = Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), key]);
  const publicKey = createPublicKey({ key: spki, format: 'der', type: 'spki' });
  assert(verify(null, message, publicKey, signature),
    'Invalid Ed25519 signature');
}

function checkJsonSignature(key, signature, body) {
  checkSignature(key, Buffer.from(signature, 'base64'), Buffer.from(canonical(body)));
}

function checkInclusion(document, leafIndex, treeSize, path, rootHash) {
  assert(Number.isSafeInteger(leafIndex) && Number.isSafeInteger(treeSize));
  assert(leafIndex >= 0 && leafIndex < treeSize);
  let index = BigInt(leafIndex);
  let last = BigInt(treeSize - 1);
  let digest = hash(Buffer.of(0), canonical(document));
  const leafHash = digest.toString('hex');
  for (const hex of path) {
    assert(last > 0n && /^[a-f0-9]{64}$/.test(hex), 'Invalid Merkle audit path');
    const sibling = Buffer.from(hex, 'hex');
    if ((index & 1n) || index === last) {
      digest = hash(Buffer.of(1), sibling, digest);
      while (index > 0n && !(index & 1n)) {
        index >>= 1n;
        last >>= 1n;
      }
    } else {
      digest = hash(Buffer.of(1), digest, sibling);
    }
    index >>= 1n;
    last >>= 1n;
  }
  assert.equal(last, 0n);
  assert.equal(digest.toString('hex'), rootHash, 'Merkle root mismatch');
  return leafHash;
}

function checkLegion() {
  const downloaded = read('record.json');
  assert.deepEqual(downloaded, record, 'Downloaded leaf differs from the archived case');
  const keyring = readFileSync(new URL('keyring.jsonl', import.meta.url), 'utf8')
    .trim().split('\n').map((line) => JSON.parse(line));
  const root = Buffer.from(keyring[0].public_key_b64, 'base64');
  assert.equal(pin(root), rootPin);

  // This fixed snapshot has registrations only. Reject unsupported key events.
  const keys = new Map();
  let previous = '0'.repeat(64);
  for (const entry of keyring) {
    const { hash: entryHash, self_sig, endorsement_sig, ...body } = entry;
    const key = Buffer.from(body.public_key_b64, 'base64');
    assert.equal(body.type, 'key_register');
    assert.equal(body.alg, 'Ed25519');
    assert.equal(body.prev_hash, previous);
    assert.equal(body.key_id, 'k1:' + pin(key).slice(0, 32));
    // LEGION treats the legacy root registration as pinned genesis.
    if (previous !== '0'.repeat(64)) {
      assert.equal(hash(canonical(body)).toString('hex'), entryHash);
      checkJsonSignature(key, self_sig, body);
      assert.equal(body.endorsed_by, keyring[0].key_id);
      checkJsonSignature(root, endorsement_sig, body);
    }
    keys.set(pin(key), { key, body });
    previous = entryHash;
  }

  const { signature_ed25519, ...recordBody } = downloaded;
  const { sth } = read('head.json');
  const head = sth.tree_head;
  for (const [keyId, timestamp, signature, body] of [
    [recordBody.key_id, recordBody.observed_at, signature_ed25519, recordBody],
    [head.issuer_pin_sha256, head.timestamp, sth.signature_ed25519, head],
  ]) {
    const signer = keys.get(keyId);
    assert.equal(signer?.body.purpose, 'mcp-tlog');
    assert(Date.parse(signer.body.valid_from) <= Date.parse(timestamp));
    checkJsonSignature(signer.key, signature, body);
  }

  const proof = read('inclusion.json');
  assert.equal(proof.leaf_index, recordBody.leaf_index);
  assert.equal(proof.tree_size, head.tree_size);
  const leafHash = checkInclusion(downloaded, proof.leaf_index, proof.tree_size,
    proof.audit_path, head.root_sha256);
  return {
    verified: true,
    leafIndex: proof.leaf_index,
    treeSize: proof.tree_size,
    headTimestamp: head.timestamp,
    pathLength: proof.audit_path.length,
    leafHash,
    rootHash: head.root_sha256,
    signingKey: recordBody.key_id,
    rootKeyPin: rootPin,
  };
}

const legionVerification = checkLegion();

function decodeMultibase58(value) {
  assert(value.startsWith('z'));
  const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  const digits = value.slice(1);
  let number = 0n;
  for (const digit of digits) {
    const index = alphabet.indexOf(digit);
    assert(index >= 0);
    number = number * 58n + BigInt(index);
  }
  const hex = number ? number.toString(16) : '';
  return Buffer.concat([
    Buffer.alloc(digits.match(/^1*/)[0].length),
    Buffer.from(hex.length % 2 ? '0' + hex : hex, 'hex'),
  ]);
}

function checkHistor(states) {
  const did = 'did:key:z6Mkw1CVxsPj9utYp7VXWEbuuGM9Ev47itwKu1UfKd5ByxR9';
  const fingerprint = did.slice('did:key:'.length);
  const method = did + '#' + fingerprint;
  const keyBytes = decodeMultibase58(fingerprint);
  assert.equal(keyBytes.subarray(0, 2).toString('hex'), 'ed01');
  const key = keyBytes.subarray(2);
  const issuer = read('histor-issuer.json');
  assert.equal(issuer.did, did);
  assert.equal(issuer.publicKeyHex, key.toString('hex'));

  const head = read('histor-head.json');
  const { signature, ...headBody } = head;
  assert.equal(headBody.log, did);
  assert.equal(headBody.type, 'histor.sth/v1');
  assert.equal(signature.alg, 'Ed25519');
  assert.equal(signature.verificationMethod, method);
  checkJsonSignature(key, signature.value, headBody);

  const labels = states.map(({ digest, observedAt }, index) => {
    const label = read('histor-label-' + (index + 1) + '.json');
    const inclusion = read('histor-proof-' + (index + 1) + '.json');
    const { proof, ...body } = label;
    const { proofValue, ...options } = proof;
    assert.equal(body.issuer.id, did);
    assert(body.type.includes('MCPTrustLabel'));
    assert.equal(proof.verificationMethod, method);
    assert.equal(proof.type, 'DataIntegrityProof');
    assert.equal(proof.cryptosuite, 'eddsa-jcs-2022');
    assert.equal(proof.proofPurpose, 'assertionMethod');
    assert.deepEqual(options['@context'], body['@context']);
    const signatureBytes = decodeMultibase58(proofValue);
    assert.equal(signatureBytes.length, 64);
    checkSignature(key, signatureBytes, Buffer.concat([
      hash(canonical(options)), hash(canonical(body)),
    ]));

    assert.equal(inclusion.labelId, label.id);
    assert.deepEqual(inclusion.sth, head);
    const leafHash = checkInclusion(label, inclusion.leafIndex, head.treeSize,
      inclusion.inclusionProof, head.rootHash);
    const observation = body.credentialSubject.mcpTrustLabel;
    assert.equal(observation.profile, 'MTL/1');
    assert.equal(observation.server.name, histor.snapshot.name);
    assert.equal(observation.observedAt, observedAt);
    const tools = histor.toolsets[digest];
    assert.equal(observation.toolSet.count, tools.length);
    assert.equal(observation.toolSet.digestSRI, digest);
    assert.equal('sha256-' + hash(canonical(tools)).toString('base64'), digest);
    return { labelId: label.id, observedAt, digest, leafIndex: inclusion.leafIndex, leafHash };
  });

  return {
    verified: true, issuer: did, treeSize: head.treeSize,
    headTimestamp: head.timestamp, rootHash: head.rootHash, labels,
  };
}

function fingerprints(tools) {
  return Object.fromEntries(tools.map((tool) => {
    const fields = Object.fromEntries(['name', 'description', 'inputSchema']
      .filter((key) => Object.hasOwn(tool, key)).map((key) => [key, tool[key]]));
    return [tool.name, createHash('sha256').update(canonical(fields)).digest('hex')];
  }));
}

assert.equal(record.server_id, histor.snapshot.name);
const legion = Object.fromEntries(record.tools_fingerprint.per_tool_sha256);
function compare(digest) {
  const local = fingerprints(histor.toolsets[digest]);
  const names = [...new Set([...Object.keys(legion), ...Object.keys(local)])].sort();
  return {
    same: names.filter((name) => local[name] === legion[name]).length,
    modified: names.filter((name) => name in local && name in legion && local[name] !== legion[name]),
    onlyHistor: names.filter((name) => !(name in legion)),
    onlyLegion: names.filter((name) => !(name in local)),
  };
}

const { from, to, at } = histor.transition;
const previous = histor.history.find((change) => change.to === from && change.at < at);
assert(previous && previous.at <= record.observed_at && record.observed_at < at);
assert.deepEqual(fingerprints(histor.toolsets[from]), legion);
const after = compare(to);
const snapshot = compare(histor.snapshot.toolSetDigest);
assert(after.modified.length + after.onlyHistor.length + after.onlyLegion.length > 0);
assert(snapshot.modified.length + snapshot.onlyHistor.length + snapshot.onlyLegion.length > 0);
const historVerification = checkHistor([
  { digest: from, observedAt: previous.at },
  { digest: to, observedAt: at },
  { digest: histor.snapshot.toolSetDigest, observedAt: histor.snapshot.unchangedSince },
]);
console.log(JSON.stringify({
  legionVerification,
  historVerification,
  server: record.server_id,
  algorithm: record.tools_fingerprint.algo,
  legionObservedAt: record.observed_at,
  historicalMatch: { from: previous.at, until: at, ...compare(from) },
  immediatelyAfterChange: { at, ...after },
  novemberSnapshot: { lastObserved: histor.snapshot.lastObserved, ...snapshot },
}, null, 2));
