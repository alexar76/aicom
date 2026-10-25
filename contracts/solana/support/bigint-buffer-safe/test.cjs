const { test } = require('node:test');
const assert = require('node:assert/strict');
const {toBigIntLE,toBigIntBE,toBufferLE,toBufferBE} = require('./index.cjs');
test('unsigned amount encodings match independent fixed endian vectors', () => {
  assert.equal(toBufferLE(0x0807060504030201n,8).toString('hex'),'0102030405060708');
  assert.equal(toBufferBE(0x0807060504030201n,8).toString('hex'),'0807060504030201');
  assert.equal(toBigIntLE(Buffer.from('0102030405060708','hex')),0x0807060504030201n);
  assert.equal(toBigIntBE(Buffer.from('0807060504030201','hex')),0x0807060504030201n);
  for (const width of [1,2,4,8,16,32]) {
    const maximum = (1n << BigInt(width*8))-1n;
    assert.equal(toBufferLE(maximum,width).toString('hex'),'ff'.repeat(width));
    assert.equal(toBufferBE(maximum,width).toString('hex'),'ff'.repeat(width));
    assert.equal(toBigIntLE(Buffer.alloc(width,255)),maximum);
    assert.equal(toBigIntBE(Buffer.alloc(width,255)),maximum);
    assert.equal(toBufferLE(0n,width).toString('hex'),'00'.repeat(width));
    assert.equal(toBigIntLE(toBufferLE(maximum-1n,width)),maximum-1n);
    assert.equal(toBigIntBE(toBufferBE(maximum-1n,width)),maximum-1n);
    assert.throws(()=>toBufferLE(maximum+1n,width),RangeError);
  }
  assert.equal(toBigIntLE(Buffer.alloc(0)),0n);
  assert.equal(toBigIntBE(Buffer.alloc(0)),0n);
  assert.equal(toBufferLE(0n,0).length,0);
});
test('untrusted widths and signed values cannot wrap, truncate or allocate unbounded memory', () => {
  for (const width of [-1,0.5,NaN,Infinity,4097,Number.MAX_SAFE_INTEGER]) assert.throws(()=>toBufferLE(1n,width),RangeError);
  assert.throws(()=>toBufferBE(-1n,8),RangeError);
  assert.throws(()=>toBufferLE(1,8),TypeError);
  assert.throws(()=>toBigIntLE(Buffer.alloc(4097)),RangeError);
  assert.throws(()=>toBigIntBE('01'),TypeError);
});
