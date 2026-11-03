// The external fixture is public Rooterberg test data, never a user's key.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../../..');
const requireOz = createRequire(path.join(root, 'contracts/evm/lib/openzeppelin-contracts/package.json'));
const { ec: EC } = requireOz('elliptic');
const { p521 } = requireOz('@noble/curves/nist.js');
const provenance = require('./provenance.json');
const bytes = fs.readFileSync(process.argv[2]);
assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), provenance.vector_source.sha256);
const vectors = JSON.parse(bytes).tests;
const ec = new EC('p521');
const mismatches = [];
for (const vector of vectors) {
  const digest = crypto.createHash('sha512').update(Buffer.from(vector.msg, 'hex')).digest();
  const signature = ec.sign(digest, vector.privateKey, 'hex');
  const expected = Buffer.from(vector.sig, 'hex');
  const noble = p521.sign(digest, Buffer.from(vector.privateKey.padStart(132, '0'), 'hex'),
    { prehash: false, lowS: false, format: 'der' });
  assert.deepEqual(Buffer.from(noble), expected, `Independent implementation, case ${vector.tcId}`);
  assert(ec.verify(digest, signature, ec.keyFromPrivate(vector.privateKey, 'hex')));
  if (signature.toDER('hex') !== vector.sig) mismatches.push(vector.tcId);
}
console.log(JSON.stringify({ vectors: vectors.length, elliptic_mismatches: mismatches.length,
  first_mismatches: mismatches.slice(0, 10), noble_mismatches: 0,
  installed_version: requireOz('elliptic/package.json').version }));
if (process.argv.includes('--baseline')) assert(mismatches.length > 0, 'Baseline must reproduce CVE');
else assert.deepEqual(mismatches, [], 'Backport must match every reference signature');
