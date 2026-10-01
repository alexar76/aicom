'use strict';

const assert = require('node:assert/strict');
const receiptUrl = require('./receipt-url.js');

assert.equal(receiptUrl.validate(
  'https://modelmarket.dev/ai-market/v2/p/provenance/receipt/urn:uuid:abc'
).ok, true);
assert.equal(receiptUrl.fromSearch(
  '?receipt_url=' + encodeURIComponent(
    'https://modelmarket.dev/ai-market/v2/p/provenance/receipt/urn:uuid:abc'
  )
).ok, true);

for (const unsafe of [
  'http://modelmarket.dev/ai-market/v2/p/provenance/receipt/x',
  'https://evil.example/ai-market/v2/p/provenance/receipt/x',
  'https://modelmarket.dev.evil.example/ai-market/v2/p/provenance/receipt/x',
  'https://user:pass@modelmarket.dev/ai-market/v2/p/provenance/receipt/x',
  'https://modelmarket.dev/ai-market/v2/p/provenance/verify/x',
  'https://modelmarket.dev/ai-market/v2/p/provenance/receipt/x/extra',
  'https://modelmarket.dev/ai-market/v2/p/provenance/receipt/x?next=evil',
]) {
  assert.equal(receiptUrl.validate(unsafe).ok, false, unsafe);
}

console.log('receipt-url: ok');
