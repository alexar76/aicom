'use strict';

// AWR/2 section 6.3.1 rule 3 on every Ed25519 backend, from the vector the SDKs share
// (aimarket-sdks/test-vectors/ed25519_small_order.json). Until 2026-11-03 only the tweetnacl
// path refused these forgeries; WebCrypto, the default in Node and current browsers, accepted
// them for every message, and so did the BigInt fallback.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const verifier = require('./verifier.js');

const v = JSON.parse(fs.readFileSync(
  path.join(__dirname, '../../../aimarket-sdks/test-vectors/ed25519_small_order.json'), 'utf8'));
const hex = (h) => new Uint8Array(Buffer.from(h, 'hex'));
const utf8 = (s) => new TextEncoder().encode(s);

async function main() {
  // undefined = what callers get: WebCrypto where the host has Ed25519, else the fallback.
  for (const backend of [undefined, 'bigint']) {
    const opts = backend ? { forceEd25519Backend: backend } : undefined;
    const name = backend || 'default';
    const t = v.rfc8032Test1;
    assert.equal(await verifier.verifyEd25519(hex(t.publicKeyHex), hex(t.signatureHex), utf8(t.message), opts),
      true, `${name}: RFC 8032 TEST 1`);
    for (const f of v.forgeries) {
      for (const m of f.messages) {
        assert.equal(await verifier.verifyEd25519(hex(f.publicKeyHex), hex(f.signatureHex), utf8(m), opts),
          false, `${name}: ${f.name}, message ${JSON.stringify(m)}`);
      }
    }
  }
  console.log('ed25519-small-order: ok');
}

main().catch((e) => { console.error(e); process.exit(1); });
