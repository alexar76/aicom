// What WARDEN's static scan takes from Node, in plain JavaScript for the HESTIA sandbox
// (QuickJS for WASI: no Node, no Web Crypto). Only what the scan reaches is here:
// node:crypto createHash("sha256"), Buffer.from(text, "base64url") with toString("base64url"),
// and a fatal UTF-8 TextDecoder. Each is checked against Node's own in hestia-agents/tests.

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

export function utf8Bytes(text) {
  const out = [];
  for (const ch of text) {
    let c = ch.codePointAt(0);
    if (c >= 0xd800 && c <= 0xdfff) c = 0xfffd; // a lone surrogate encodes as U+FFFD, as in Node
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
  }
  return new Uint8Array(out);
}

export function sha256(bytes) {
  const h = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                             0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const total = bytes.length;
  const padded = new Uint8Array(((total + 9 + 63) >> 6) << 6);
  padded.set(bytes);
  padded[total] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(total / 0x20000000));
  view.setUint32(padded.length - 4, (total << 3) >>> 0);
  const w = new Uint32Array(64);
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const a = w[i - 15], b = w[i - 2];
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, k] = h;
    for (let i = 0; i < 64; i++) {
      const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
      const t1 = (k + s1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0;
      const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
      const t2 = (s0 + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
      k = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += k;
  }
  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  for (let i = 0; i < 8; i++) outView.setUint32(i * 4, h[i]);
  return out;
}

const STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

function encode(bytes, alphabet, pad) {
  let out = "";
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    out += alphabet[n >> 18] + alphabet[(n >> 12) & 63] + alphabet[(n >> 6) & 63] + alphabet[n & 63];
  }
  if (i < bytes.length) {
    const n = (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8);
    out += alphabet[n >> 18] + alphabet[(n >> 12) & 63];
    out += i + 1 < bytes.length ? alphabet[(n >> 6) & 63] : "";
    if (pad) out += i + 1 < bytes.length ? "=" : "==";
  }
  return out;
}

/** Node's lenient base64 decoding: either alphabet, padding ignored, other characters skipped. */
function decode(text) {
  const out = [];
  let bits = 0, count = 0;
  for (const ch of text) {
    if (ch === "=") break;
    let v = STD.indexOf(ch);
    if (v < 0) v = URL.indexOf(ch);
    if (v < 0) continue;
    bits = (bits << 6) | v;
    count += 6;
    if (count >= 8) {
      count -= 8;
      out.push((bits >> count) & 0xff);
      bits &= (1 << count) - 1;
    }
  }
  return new Uint8Array(out);
}

class Bytes extends Uint8Array {
  toString(encoding) {
    if (encoding === "base64url") return encode(this, URL, false);
    if (encoding === "base64") return encode(this, STD, true);
    if (encoding === "hex") return Array.from(this, (b) => b.toString(16).padStart(2, "0")).join("");
    return new TextDecoder("utf-8").decode(this);
  }
}

export const Buffer = {
  from(value, encoding) {
    if (typeof value === "string") {
      if (encoding === "base64url" || encoding === "base64") {
        const raw = decode(value);
        return new Bytes(raw.buffer, raw.byteOffset, raw.length);
      }
      const raw = utf8Bytes(value);
      return new Bytes(raw.buffer, raw.byteOffset, raw.length);
    }
    return new Bytes(Uint8Array.from(value));
  },
};

export class TextDecoder {
  constructor(label = "utf-8", options = {}) {
    if (String(label).toLowerCase().replace("-", "") !== "utf8") throw new RangeError("only utf-8");
    this.fatal = Boolean(options.fatal);
  }
  decode(input) {
    const b = input instanceof Uint8Array ? input : new Uint8Array(input ?? []);
    let out = "";
    for (let i = 0; i < b.length;) {
      const x = b[i];
      let need = 0, cp = 0, min = 0;
      if (x < 0x80) { out += String.fromCharCode(x); i++; continue; }
      if (x >= 0xc2 && x <= 0xdf) { need = 1; cp = x & 0x1f; min = 0x80; }
      else if (x >= 0xe0 && x <= 0xef) { need = 2; cp = x & 0x0f; min = 0x800; }
      else if (x >= 0xf0 && x <= 0xf4) { need = 3; cp = x & 0x07; min = 0x10000; }
      else need = -1;
      let ok = need > 0 && i + need < b.length;
      for (let j = 1; ok && j <= need; j++) {
        const y = b[i + j];
        if (y === undefined || (y & 0xc0) !== 0x80) ok = false;
        else cp = (cp << 6) | (y & 0x3f);
      }
      if (ok && (cp < min || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))) ok = false;
      if (!ok) {
        if (this.fatal) throw new TypeError("The encoded data was not valid for encoding utf-8");
        out += "�";
        i++;
        continue;
      }
      out += String.fromCodePoint(cp);
      i += need + 1;
    }
    return out;
  }
}

class Hash {
  constructor() { this.parts = []; }
  update(data, encoding) {
    this.parts.push(typeof data === "string" ? utf8Bytes(data) : Uint8Array.from(data));
    void encoding;
    return this;
  }
  digest(encoding) {
    const size = this.parts.reduce((n, p) => n + p.length, 0);
    const all = new Uint8Array(size);
    let at = 0;
    for (const p of this.parts) { all.set(p, at); at += p.length; }
    const out = sha256(all);
    if (encoding === "hex") return Array.from(out, (b) => b.toString(16).padStart(2, "0")).join("");
    if (encoding === "base64") return encode(out, STD, true);
    if (encoding === "base64url") return encode(out, URL, false);
    return Buffer.from(out);
  }
}

export function createHash(algorithm) {
  if (String(algorithm).toLowerCase() !== "sha256") throw new Error("only sha256 is available here");
  return new Hash();
}

export function randomBytes() {
  throw new Error("randomBytes is not available in the HESTIA sandbox");
}
