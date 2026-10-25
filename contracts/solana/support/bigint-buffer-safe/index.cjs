'use strict';
// SPL amount layouts use these unsigned conversions at widths 1..32 bytes.
// Keep the legacy API while rejecting invalid widths, negative values, overflow,
// and oversized allocations. No native binding or unsafe memory access is used.
const MAX_BYTES = 4096;
function checkedBytes(value) {
  if (!Buffer.isBuffer(value)) throw new TypeError('Expected a Buffer');
  if (value.length > MAX_BYTES) throw new RangeError('Integer buffer is too large');
  return value;
}
function toBigIntLE(value) {
  const bytes = checkedBytes(value);
  let result = 0n;
  for (let i = bytes.length - 1; i >= 0; i--) result = (result << 8n) | BigInt(bytes[i]);
  return result;
}
function toBigIntBE(value) {
  let result = 0n;
  for (const byte of checkedBytes(value)) result = (result << 8n) | BigInt(byte);
  return result;
}
function encode(value, width, littleEndian) {
  if (typeof value !== 'bigint') throw new TypeError('Expected a bigint');
  if (!Number.isSafeInteger(width) || width < 0 || width > MAX_BYTES) throw new RangeError('Invalid integer width');
  if (value < 0n || (value >> BigInt(width * 8)) !== 0n) throw new RangeError('Unsigned integer does not fit the requested width');
  const result = Buffer.alloc(width);
  for (let i = 0; i < width; i++) {
    result[littleEndian ? i : width - 1 - i] = Number(value & 255n);
    value >>= 8n;
  }
  return result;
}
exports.toBigIntLE = toBigIntLE;
exports.toBigIntBE = toBigIntBE;
exports.toBufferLE = (value, width) => encode(value, width, true);
exports.toBufferBE = (value, width) => encode(value, width, false);
