const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const path = require('node:path');
const { createRequire } = require('node:module');
const test = require('node:test');
const root = path.resolve(__dirname, '../../..');
const oz = createRequire(path.join(root, 'contracts/evm/lib/openzeppelin-contracts/package.json'));
const elliptic = oz('elliptic');
const ethers5 = oz('@ethersproject/signing-key');
const ethers6 = oz('ethers');
const secp = oz('secp256k1/elliptic');
const { p256, p521 } = oz('@noble/curves/nist.js');
const hex = bytes => Buffer.from(bytes).toString('hex');

test('all elliptic consumers resolve the pinned backport', () => {
  assert.equal(oz('elliptic/package.json').version, '6.6.1+aicom.1');
  for (const consumer of ['@ethersproject/signing-key', 'secp256k1']) {
    const fromConsumer = createRequire(oz.resolve(consumer));
    assert.equal(fromConsumer.resolve('elliptic'), oz.resolve('elliptic'));
  }
});

test('CVE-2025-14505: leading-zero nonce matches Rooterberg case 29', () => {
  const vector = require('./p521-leading-zero.fixture.json');
  const ec = new elliptic.ec('p521');
  const digest = Buffer.from(vector.digest, 'hex');
  const key = Buffer.from(vector.public_test_private_key.padStart(132, '0'), 'hex');
  const signature = ec.sign(digest, key);
  assert.equal(signature.toDER('hex'), vector.expected_signature);
  assert.equal(hex(p521.sign(digest, key, { prehash: false, lowS: false, format: 'der' })),
    vector.expected_signature);
});

test('ECDSA signs and verifies leading-zero digests identically to Noble', () => {
  for (const [curve, noble, size, hash] of [
    ['p256', p256, 32, 'sha256'], ['p521', p521, 66, 'sha512'],
  ]) {
    const ec = new elliptic.ec(curve);
    const key = Buffer.alloc(size); key[size - 1] = 7; // Public disposable test key.
    for (let i = 0; i < 12; i++) {
      const digest = crypto.createHash(hash).update(`aicom-nonce-regression-${i}`).digest();
      digest.fill(0, 0, i % 4);
      const expected = noble.sign(digest, key, { prehash: false, lowS: false, format: 'der' });
      for (const message of [digest, [...digest], hex(digest)]) {
        const signature = ec.sign(message, key);
        assert.equal(signature.toDER('hex'), hex(expected));
        assert(ec.verify(message, signature, ec.keyFromPrivate(key)));
      }
    }
  }
});

test('custom nonce callback retains its scalar semantics', () => {
  const ec = new elliptic.ec('p521');
  const BN = ec.n.constructor;
  const digest = Buffer.alloc(64, 3);
  const sig = ec.sign(digest, '07', { k: () => new BN(17) });
  assert(ec.verify(digest, sig, ec.keyFromPrivate('07', 'hex')));
  assert(sig.r.eq(ec.g.mul(new BN(17)).getX().umod(ec.n)));
});

test('ethers v5 and secp256k1 JS fallback retain Ethereum signing and recovery', () => {
  const privateKey = Buffer.alloc(32); privateKey[31] = 11;
  const signing5 = new ethers5.SigningKey(privateKey);
  const signing6 = new ethers6.SigningKey(privateKey);
  for (let i = 0; i < 32; i++) {
    const digest = crypto.createHash('sha256').update(`aicom-ethereum-compat-${i}`).digest();
    digest.fill(0, 0, i % 4);
    const expected = signing6.sign(digest);
    const legacy = signing5.signDigest(digest);
    assert.equal(legacy.r, expected.r); assert.equal(legacy.s, expected.s);
    assert.equal(legacy.recoveryParam, expected.yParity);
    assert.equal(ethers5.recoverPublicKey(digest, legacy), signing6.publicKey);
    const nativeFallback = secp.ecdsaSign(digest, privateKey);
    assert.equal(hex(nativeFallback.signature), expected.r.slice(2) + expected.s.slice(2));
    assert.equal(nativeFallback.recid, expected.yParity);
    assert(secp.ecdsaVerify(nativeFallback.signature, digest, secp.publicKeyCreate(privateKey)));
    assert.equal(hex(secp.ecdsaRecover(nativeFallback.signature, nativeFallback.recid, digest, false)),
      signing6.publicKey.slice(2));
  }
});
