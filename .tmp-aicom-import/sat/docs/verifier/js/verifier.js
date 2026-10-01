/**
 * AWR/2 browser verifier — verify.modelmarket.dev
 * =================================================
 *
 * Client-side verifier for AWR (Agent Work Receipt) documents, normatively
 * specified in `awr/SPEC.md` (AWR 2.0.0). Section references below are to that
 * document.
 *
 * What this file implements:
 *
 *   §4   RFC 8785 JSON Canonicalization Scheme (JCS) with the AWR number
 *        restriction, duplicate-key rejection and lone-surrogate rejection.
 *   §5   `did:key` parsing (hand-written base58btc) and the optional
 *        `publicKeyJwk` consistency check.
 *   §6   `eddsa-jcs-2022` Data Integrity proof verification:
 *        hashData = SHA-256(JCS(proofConfig)) || SHA-256(JCS(document−proof)),
 *        Ed25519 over those 64 bytes.
 *   §8   Work-chain resolution over caller-supplied documents (never network).
 *   §9   Bundles.
 *   §10  Profiles L0/L1/L2.
 *   §11  Result shape and the reason-code registry.
 *   §12  AWR/1 legacy verification, BOTH dialects, always flagged
 *        `AWR-LEGACY-001`.
 *
 * Deliberate non-features (all normative):
 *   - No network access of any kind during verification (§13.5). No `@context`
 *     dereferencing, no parent fetching, no revocation lookup.
 *   - TEE / zk attestations are opaque (§7.3). We do NOT check their inner
 *     signatures; an earlier revision of this file verified a TEE attestation
 *     with the *receipt issuer's* key, which proves only that the party making
 *     the claim also wrote it down while presenting as hardware evidence. The
 *     honest outcome is the `AWR-ENV-001` warning.
 *   - Age is never invalidity (§11.3). An old receipt is exactly as sound as a
 *     fresh one; any age threshold is caller policy (`opts.maxAgeDays`).
 *
 * Runtime: browser (script tag, no build step) or Node (`require`). The only
 * host API used is WebCrypto `crypto.subtle.digest` (SHA-256/SHA-512), present
 * in every target browser and in Node >= 18 as a global. Ed25519 verification
 * prefers `crypto.subtle` when the host implements the Ed25519 algorithm,
 * then a `nacl` global if a page vendored TweetNaCl, and otherwise falls back
 * to the self-contained BigInt implementation at the bottom of this file — so
 * the page keeps working with zero external dependencies and fully offline.
 */
'use strict';

(function (root) {

  // ── §3.1 / §5.1 constants ────────────────────────────────────────────────
  var VC2_CONTEXT = 'https://www.w3.org/ns/credentials/v2';
  var AWR2_CONTEXT = 'https://verify.modelmarket.dev/ns/awr/v2';
  var AWR_TYPES = ['WorkReceipt', 'VerificationVerdict', 'BlameAttestation'];
  var DID_KEY_PREFIX = 'did:key:';
  var ED25519_MULTICODEC = [0xed, 0x01];        // unsigned-varint `ed25519-pub`
  // §5.1: multicodecs that name a real public key of a type AWR/2 does not
  // support. Telling these apart from garbage is AWR-KEY-004 vs AWR-KEY-002.
  var OTHER_KEY_MULTICODECS = {
    e701: 'secp256k1-pub',
    ec01: 'x25519-pub',
    ea01: 'bls12_381-g1-pub',
    eb01: 'bls12_381-g2-pub',
    8024: 'p256-pub',
    8124: 'p384-pub',
    8224: 'p521-pub',
    8524: 'rsa-pub'
  };
  var CRYPTOSUITE = 'eddsa-jcs-2022';
  var PROOF_TYPE = 'DataIntegrityProof';
  var LEGACY_PROOF_TYPE = 'Ed25519Signature2018';

  var MAX_SAFE_AWR_INT = 9007199254740991;      // §4.3  2^53 − 1
  var WORK_STATUS = ['succeeded', 'failed', 'refused', 'timeout', 'partial'];
  var VERDICTS = ['pass', 'fail', 'inconclusive'];
  var FAILURE_CLASSES = ['wrong-output', 'malformed-output', 'unavailable', 'timeout',
                         'policy-violation', 'upstream-input', 'cost-overrun', 'unknown'];

  // §8.2 defaults, both configurable. §13.4 input bounds.
  var DEFAULTS = {
    chainMaxDepth: 64,
    chainMaxNodes: 1024,
    maxJsonDepth: 128,
    maxInputBytes: 8 * 1024 * 1024,
    clockSkewSeconds: 300,
    maxAgeDays: null,           // null = no age policy; see §11.3
    // §12.4: the AWR/1 signing key supplied OUT OF BAND, as 32 raw bytes. When
    // set it is the only key tried; nothing the document carries is substituted
    // for it or used as a fallback.
    expectedKey: null,
    // §12.3: decline AWR/1 entirely (AWR-LEGACY-005). §12 support is OPTIONAL.
    noLegacy: false
  };

  var RFC3339_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
  var ABSOLUTE_URI = /^[A-Za-z][A-Za-z0-9+\-.]*:[^\s]*$/;
  var DECIMAL_STRING = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/;          // §3.3 price.amount
  var UNIT_DECIMAL_STRING = /^(0(\.[0-9]+)?|1(\.0+)?)$/;          // §3.4 score
  var ISO4217 = /^[A-Z]{3}$/;
  // §3.2: the base64 must be CANONICAL. 32 bytes is not a multiple of 3, so the 43rd
  // character carries four bits that decode to nothing and base64 admits 16 spellings of
  // every digest. A digest reference is an identity (AWR-CHAIN-006 compares these strings),
  // so only the spelling with those bits zero — final character in [AEIMQUYcgkosw048] — is
  // accepted. This verifier accepted all 16 until the rule was written down.
  var SRI_SHA256 = /^sha256-[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$/;

  // ─────────────────────────────────────────────────────────────────────────
  // 1. Errors and the §11.1 findings collector
  // ─────────────────────────────────────────────────────────────────────────

  /** A canonicalization/parse failure that carries a §11.2 reason code. */
  function AwrError(code, detail) {
    var e = new Error(code + ': ' + detail);
    e.name = 'AwrError';
    e.code = code;
    e.detail = detail;
    return e;
  }

  function Findings() {
    this.reasons = [];
    this.warnings = [];
    this._seen = Object.create(null);
  }
  Findings.prototype._push = function (list, code, severity, detail) {
    var key = severity + '\u0000' + code + '\u0000' + detail;
    if (this._seen[key]) return;
    this._seen[key] = true;
    list.push({ code: code, severity: severity, detail: String(detail) });
  };
  /** §11.1: `valid` is false iff at least one entry of severity `error` exists. */
  Findings.prototype.error = function (code, detail) {
    this._push(this.reasons, code, 'error', detail);
  };
  Findings.prototype.warn = function (code, detail) {
    this._push(this.warnings, code, 'warning', detail);
  };
  Findings.prototype.hasCode = function (code) {
    for (var i = 0; i < this.reasons.length; i++) if (this.reasons[i].code === code) return true;
    return false;
  };
  Findings.prototype.valid = function () { return this.reasons.length === 0; };

  // ─────────────────────────────────────────────────────────────────────────
  // 2. Byte helpers — all hand-written so the module has no dependencies
  // ─────────────────────────────────────────────────────────────────────────

  function utf8Encode(str) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(str);
    var out = [], i, c;                                   // pragmatic fallback
    for (i = 0; i < str.length; i++) {
      c = str.codePointAt(i);
      if (c > 0xffff) i++;
      if (c < 0x80) out.push(c);
      else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
      else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
      else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    }
    return new Uint8Array(out);
  }

  var B64_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

  function base64Encode(bytes) {
    var out = '', i, a, b, c;
    for (i = 0; i < bytes.length; i += 3) {
      a = bytes[i]; b = i + 1 < bytes.length ? bytes[i + 1] : -1; c = i + 2 < bytes.length ? bytes[i + 2] : -1;
      out += B64_ALPHABET[a >> 2];
      out += B64_ALPHABET[((a & 3) << 4) | (b >= 0 ? b >> 4 : 0)];
      out += b >= 0 ? B64_ALPHABET[((b & 15) << 2) | (c >= 0 ? c >> 6 : 0)] : '=';
      out += c >= 0 ? B64_ALPHABET[c & 63] : '=';
    }
    return out;
  }

  /** Decodes standard or URL-safe base64, with or without padding. */
  function base64Decode(str) {
    var s = String(str).replace(/-/g, '+').replace(/_/g, '/').replace(/[\r\n\t ]/g, '');
    var pad = s.indexOf('=');
    if (pad >= 0) s = s.slice(0, pad);
    var out = [], acc = 0, bits = 0, i, v;
    for (i = 0; i < s.length; i++) {
      v = B64_ALPHABET.indexOf(s.charAt(i));
      if (v < 0) throw AwrError('AWR-CANON-005', 'invalid base64 character at offset ' + i);
      acc = (acc << 6) | v; bits += 6;
      if (bits >= 8) { bits -= 8; out.push((acc >> bits) & 0xff); }
    }
    return new Uint8Array(out);
  }

  // base58btc, Bitcoin alphabet (§5.1). Hand-written big-number base conversion
  // over 8-bit limbs — no BigInt needed and no dependency.
  var B58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  var B58_MAP = (function () {
    var m = Object.create(null);
    for (var i = 0; i < B58_ALPHABET.length; i++) m[B58_ALPHABET.charAt(i)] = i;
    return m;
  })();

  function base58btcDecode(str) {
    var s = String(str);
    if (s.length === 0) throw AwrError('AWR-KEY-002', 'empty base58btc string');
    var zeros = 0;
    while (zeros < s.length && s.charAt(zeros) === '1') zeros++;
    var limbs = [];                                   // little-endian byte limbs
    for (var i = zeros; i < s.length; i++) {
      var carry = B58_MAP[s.charAt(i)];
      if (carry === undefined) {
        throw AwrError('AWR-KEY-002', 'character ' + JSON.stringify(s.charAt(i)) +
                       ' is not in the base58btc alphabet');
      }
      for (var j = 0; j < limbs.length; j++) {
        var t = limbs[j] * 58 + carry;
        limbs[j] = t & 0xff;
        carry = t >>> 8;
      }
      while (carry > 0) { limbs.push(carry & 0xff); carry >>>= 8; }
    }
    var out = new Uint8Array(zeros + limbs.length);
    for (var k = 0; k < limbs.length; k++) out[zeros + k] = limbs[limbs.length - 1 - k];
    return out;
  }

  function base58btcEncode(bytes) {
    var zeros = 0;
    while (zeros < bytes.length && bytes[zeros] === 0) zeros++;
    var digits = [];
    for (var i = zeros; i < bytes.length; i++) {
      var carry = bytes[i];
      for (var j = 0; j < digits.length; j++) {
        var t = digits[j] * 256 + carry;
        digits[j] = t % 58;
        carry = (t / 58) | 0;
      }
      while (carry > 0) { digits.push(carry % 58); carry = (carry / 58) | 0; }
    }
    var out = '';
    for (var z = 0; z < zeros; z++) out += '1';
    for (var d = digits.length - 1; d >= 0; d--) out += B58_ALPHABET.charAt(digits[d]);
    return out;
  }

  function bytesEqual(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
    return diff === 0;
  }

  function toHex(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) s += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
    return s;
  }

  function concatBytes(a, b) {
    var out = new Uint8Array(a.length + b.length);
    out.set(a, 0); out.set(b, a.length);
    return out;
  }

  function subtle() {
    var c = (typeof root !== 'undefined' && root.crypto) ? root.crypto
          : (typeof crypto !== 'undefined' ? crypto : null);
    if (!c || !c.subtle) throw AwrError('AWR-CANON-005', 'WebCrypto (crypto.subtle) is unavailable');
    return c.subtle;
  }

  function sha256(bytes) {
    return Promise.resolve(subtle().digest('SHA-256', bytes)).then(function (b) { return new Uint8Array(b); });
  }
  function sha512(bytes) {
    return Promise.resolve(subtle().digest('SHA-512', bytes)).then(function (b) { return new Uint8Array(b); });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 3. §4.1(5) duplicate keys and §4.3 number literals — BEFORE JSON.parse
  // ─────────────────────────────────────────────────────────────────────────
  //
  // Why a scanner and not a reviver: `JSON.parse` collapses duplicate members
  // before a reviver ever sees them (the reviver is called once per *surviving*
  // property, on the already-built object), so `{"a":1,"a":2}` is
  // indistinguishable from `{"a":2}` from inside a reviver. The V8-only
  // `context.source` argument of the ES2025 reviver would give the raw text of
  // *values*, not of object bodies, and is not portable. The only portable way
  // to see both occurrences is to look at the bytes ourselves, so we run a
  // minimal JSON tokenizer over the received text first. It does no value
  // conversion — it only tracks object scopes, collects member names, and
  // bounds nesting depth (§13.4) — and then hands the text to `JSON.parse`.
  //
  // This matters cryptographically, not cosmetically: if the parser silently
  // picked the last occurrence, the *parser* would be deciding which bytes were
  // signed (§4.1).
  //
  // The same scan is the only place §4.3's number restriction can be enforced.
  // §4.3 forbids the *literal*, not the value: `2340.0` is AWR-CANON-001 even
  // though it denotes a whole number. `JSON.parse` cannot help — an IEEE-754
  // double parses `2340` and `2340.0` to the identical value, so a check on the
  // parsed value accepts `2340.0`, canonicalizes it to `2340`, and then verifies
  // a signature over bytes the issuer never produced. `2340` vs `2340.0` is the
  // exact split that made AWR/1 two incompatible dialects (§12), so this is the
  // one check that must look at the received text.

  function scanJsonForDuplicateKeys(text, maxDepth, allowNonIntegerNumbers) {
    var i = 0, n = text.length;

    function fail(msg) { throw AwrError('AWR-CANON-005', msg + ' at offset ' + i); }
    function ws() { while (i < n && (text.charAt(i) === ' ' || text.charAt(i) === '\t' || text.charAt(i) === '\n' || text.charAt(i) === '\r')) i++; }

    function str() {
      if (text.charAt(i) !== '"') fail('expected string');
      i++;
      var out = '';
      while (i < n) {
        var ch = text.charAt(i);
        if (ch === '"') { i++; return out; }
        if (ch === '\\') {
          var esc = text.charAt(i + 1);
          if (esc === 'u') {
            var hex = text.substr(i + 2, 4);
            if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail('malformed \\u escape');
            out += String.fromCharCode(parseInt(hex, 16));
            i += 6;
          } else if ('"\\/bfnrt'.indexOf(esc) >= 0) {
            out += ({ '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' })[esc];
            i += 2;
          } else fail('invalid escape');
          continue;
        }
        if (ch.charCodeAt(0) < 0x20) fail('unescaped control character in string');
        out += ch;
        i++;
      }
      fail('unterminated string');
    }

    function value(depth) {
      if (depth > maxDepth) {
        // §13.4 requires bounding nesting depth; §11.2 registers no dedicated
        // code for input limits, so the closest honest code is CANON-005.
        throw AwrError('AWR-CANON-005', 'JSON nesting deeper than the configured limit of ' + maxDepth);
      }
      ws();
      var ch = text.charAt(i);
      if (ch === '{') {
        i++;
        var seen = Object.create(null);
        ws();
        if (text.charAt(i) === '}') { i++; return; }
        for (;;) {
          ws();
          var key = str();
          if (seen[key]) {
            throw AwrError('AWR-CANON-004',
              'duplicate object property name ' + JSON.stringify(key) +
              ' — the parser would silently decide which bytes were signed');
          }
          seen[key] = true;
          ws();
          if (text.charAt(i) !== ':') fail('expected ":"');
          i++;
          value(depth + 1);
          ws();
          if (text.charAt(i) === ',') { i++; continue; }
          if (text.charAt(i) === '}') { i++; return; }
          fail('expected "," or "}"');
        }
      }
      if (ch === '[') {
        i++;
        ws();
        if (text.charAt(i) === ']') { i++; return; }
        for (;;) {
          value(depth + 1);
          ws();
          if (text.charAt(i) === ',') { i++; continue; }
          if (text.charAt(i) === ']') { i++; return; }
          fail('expected "," or "]"');
        }
      }
      if (ch === '"') { str(); return; }
      if (text.substr(i, 4) === 'true') { i += 4; return; }
      if (text.substr(i, 5) === 'false') { i += 5; return; }
      if (text.substr(i, 4) === 'null') { i += 4; return; }
      var m = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/.exec(text.slice(i));
      if (m && m[0].length) {
        checkNumberLiteral(m[0], i);
        i += m[0].length;
        return;
      }
      fail('unexpected token');
    }

    // §4.3, lexically: a fraction or exponent part is forbidden whatever it
    // denotes, and an integer literal must be within ±(2^53−1).
    function checkNumberLiteral(literal, offset) {
      if (allowNonIntegerNumbers) return;
      if (/[.eE]/.test(literal)) {
        throw AwrError('AWR-CANON-001',
          'number literal ' + literal + ' at offset ' + offset + ' has a fraction or exponent ' +
          'part; §4.3 forbids the literal, not only the value, so `2340.0` is as invalid as ' +
          '`2340.5` — carry non-whole quantities as decimal strings');
      }
      var negative = literal.charAt(0) === '-';
      var digits = negative ? literal.slice(1) : literal;
      // Compare as decimal text: Number() would round past 2^53 and lose the case.
      var limit = '9007199254740991';
      if (digits.length > limit.length || (digits.length === limit.length && digits > limit)) {
        throw AwrError('AWR-CANON-002',
          'integer literal ' + literal + ' at offset ' + offset + ' is outside ±(2^53−1)');
      }
    }

    value(0);
    ws();
    if (i !== n) fail('trailing content after top-level JSON value');
  }

  /**
   * §6.3 step 1: parse the received bytes, rejecting duplicate keys (§4.1) and
   * forbidden number literals (§4.3).
   * Throws AwrError('AWR-CANON-001' | '002' | '004' | '005').
   *
   * `opts.allowNonIntegerNumbers` switches off the §4.3 check and exists only for
   * the AWR/1 legacy path (§12): AWR/1 predates the number restriction, so a
   * legacy document carrying `0.15` must still be checkable. Nothing on the AWR/2
   * path sets it.
   */
  function parseAwrJson(text, opts) {
    var o = withDefaults(opts);
    if (typeof text !== 'string') throw AwrError('AWR-CANON-005', 'input is not a string');
    if (text.length > o.maxInputBytes) {
      throw AwrError('AWR-CANON-005', 'input larger than the configured limit of ' + o.maxInputBytes + ' bytes');
    }
    scanJsonForDuplicateKeys(text, o.maxJsonDepth, !!o.allowNonIntegerNumbers);
    try {
      return JSON.parse(text);
    } catch (e) {
      throw AwrError('AWR-CANON-005', 'not well-formed JSON: ' + e.message);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 4. §4 RFC 8785 JCS
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * §4.1(3) string serialization: the two-character escapes where defined,
   * LOWERCASE \uXXXX for the remaining C0 controls, every other character
   * literally (no \u escaping of non-ASCII, no NFC — §4.1(2)).
   * §4.1(4): a lone surrogate terminates with AWR-CANON-003 rather than being
   * replaced by U+FFFD.
   */
  function jcsString(str, where) {
    var out = '"';
    for (var i = 0; i < str.length; i++) {
      var c = str.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff) {
        var next = i + 1 < str.length ? str.charCodeAt(i + 1) : 0;
        if (!(next >= 0xdc00 && next <= 0xdfff)) {
          throw AwrError('AWR-CANON-003', 'unpaired high surrogate U+' +
            c.toString(16).toUpperCase() + ' at ' + where);
        }
        out += str.charAt(i) + str.charAt(i + 1);
        i++;
        continue;
      }
      if (c >= 0xdc00 && c <= 0xdfff) {
        throw AwrError('AWR-CANON-003', 'unpaired low surrogate U+' +
          c.toString(16).toUpperCase() + ' at ' + where);
      }
      switch (c) {
        case 0x08: out += '\\b'; break;
        case 0x09: out += '\\t'; break;
        case 0x0a: out += '\\n'; break;
        case 0x0c: out += '\\f'; break;
        case 0x0d: out += '\\r'; break;
        case 0x22: out += '\\"'; break;
        case 0x5c: out += '\\\\'; break;
        default:
          if (c < 0x20) {
            // Lowercase hex, exactly four digits (RFC 8785 §3.2.2.2).
            out += '\\u' + ('0000' + c.toString(16)).slice(-4);
          } else {
            out += str.charAt(i);
          }
      }
    }
    return out + '"';
  }

  /** §4.3: integers only, |n| <= 2^53 − 1. Non-integers are refused, not rounded. */
  function jcsNumber(num, where) {
    if (!isFinite(num)) {
      throw AwrError('AWR-CANON-002', 'non-finite number at ' + where +
        ' (a JSON literal too large for a double parses to Infinity)');
    }
    if (!Number.isInteger(num)) {
      throw AwrError('AWR-CANON-001', 'non-integer JSON number ' + num + ' at ' + where +
        ' — carry non-whole quantities as decimal strings (§4.3)');
    }
    if (num > MAX_SAFE_AWR_INT || num < -MAX_SAFE_AWR_INT) {
      throw AwrError('AWR-CANON-002', 'integer ' + num + ' at ' + where + ' is outside ±(2^53−1)');
    }
    return num === 0 ? '0' : String(num);          // normalises -0 to "0"
  }

  function jcsSerialize(value, where, depth, maxDepth) {
    if (depth > maxDepth) {
      throw AwrError('AWR-CANON-005', 'value nesting deeper than the configured limit of ' + maxDepth);
    }
    if (value === null) return 'null';
    var t = typeof value;
    if (t === 'boolean') return value ? 'true' : 'false';
    if (t === 'number') return jcsNumber(value, where);
    if (t === 'string') return jcsString(value, where);
    if (Array.isArray(value)) {
      var items = [];
      for (var i = 0; i < value.length; i++) {
        items.push(jcsSerialize(value[i], where + '[' + i + ']', depth + 1, maxDepth));
      }
      return '[' + items.join(',') + ']';
    }
    if (t === 'object') {
      var keys = Object.keys(value);
      // RFC 8785 §3.2.3 sorts property names as arrays of UTF-16 code units
      // compared as unsigned integers. JavaScript's `<` on strings is exactly
      // that comparison (ECMA-262 IsLessThan compares code *units*, not code
      // points), and `Array.prototype.sort` with no comparator sorts by the
      // same relation after String() conversion — the keys are already strings.
      // So the default sort is correct HERE, and only here: it is correct
      // because the required order happens to be JS's native string order, not
      // because "default sort" and "sorted by spec" are the same idea. Sorting
      // by code point (e.g. via [...key] or localeCompare) would be WRONG and
      // diverges for names containing non-BMP characters, where a surrogate
      // pair (0xD800..0xDBFF) compares below U+E000..U+FFFF as code units but
      // above them as code points.
      keys.sort();
      var members = [];
      for (var k = 0; k < keys.length; k++) {
        var key = keys[k];
        members.push(jcsString(key, where + '/' + key + ' (property name)') + ':' +
                     jcsSerialize(value[key], where + '/' + key, depth + 1, maxDepth));
      }
      return '{' + members.join(',') + '}';
    }
    // undefined, function, symbol, BigInt: cannot come from JSON.parse, so a
    // caller handed us a non-JSON value.
    throw AwrError('AWR-CANON-005', 'value of type ' + t + ' at ' + where + ' is not JSON data');
  }

  /** §4.1: JCS string form of a parsed JSON value. */
  function jcsCanonicalize(value, opts) {
    var o = withDefaults(opts);
    return jcsSerialize(value, '$', 0, o.maxJsonDepth);
  }

  /** §4.1: the canonical form is UTF-8 with no trailing newline. */
  function jcsCanonicalizeBytes(value, opts) {
    return utf8Encode(jcsCanonicalize(value, opts));
  }

  /**
   * §4.4 / AWR-CANON-006 self-check: canonicalizing the canonical form again
   * must be a fixed point. Catches an escaping or sorting bug in this file
   * before it is reported as a signature failure.
   */
  function jcsSelfCheck(canonical, opts) {
    var again = jcsCanonicalize(JSON.parse(canonical), opts);
    return again === canonical;
  }

  // §4.3: `price.amount`, `score`, `confidence`, `threshold` are decimal
  // STRINGS and MUST be compared as decimals, never through a binary float.
  function decimalCompare(a, b) {
    function split(s) {
      var neg = s.charAt(0) === '-';
      var body = neg ? s.slice(1) : s;
      var dot = body.indexOf('.');
      var int = dot < 0 ? body : body.slice(0, dot);
      var frac = dot < 0 ? '' : body.slice(dot + 1);
      return { neg: neg, int: int.replace(/^0+(?=\d)/, ''), frac: frac.replace(/0+$/, '') };
    }
    var x = split(String(a)), y = split(String(b));
    if (x.neg !== y.neg) return x.neg ? -1 : 1;
    var sign = x.neg ? -1 : 1;
    if (x.int.length !== y.int.length) return x.int.length > y.int.length ? sign : -sign;
    if (x.int !== y.int) return x.int > y.int ? sign : -sign;
    var len = Math.max(x.frac.length, y.frac.length);
    var xf = (x.frac + '0'.repeat(len)).slice(0, len);
    var yf = (y.frac + '0'.repeat(len)).slice(0, len);
    if (xf === yf) return 0;
    return xf > yf ? sign : -sign;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 5. §3.2 digest references / SRI
  // ─────────────────────────────────────────────────────────────────────────

  function sriFromBytes(digestBytes) { return 'sha256-' + base64Encode(digestBytes); }

  function sriOfDocument(doc, opts) {
    // §3.2: "the UTF-8 canonical form of the referenced *secured* document",
    // i.e. proof included. A canonicalization failure is reported through the
    // returned promise so that callers have one error channel, not two.
    var bytes;
    try { bytes = jcsCanonicalizeBytes(doc, opts); } catch (e) { return Promise.reject(e); }
    return sha256(bytes).then(sriFromBytes);
  }

  /** Returns {ok:true} or {ok:false, code, detail} per §3.2. */
  function checkSri(value, where) {
    if (typeof value !== 'string' || value.length === 0) {
      return { ok: false, code: 'AWR-CHAIN-002', detail: where + ' is not a string' };
    }
    var dash = value.indexOf('-');
    var alg = dash < 0 ? '' : value.slice(0, dash);
    if (alg !== 'sha256') {
      return {
        ok: false, code: 'AWR-CHAIN-002',
        detail: where + ' uses digest algorithm ' + JSON.stringify(alg || value) +
                '; sha256 is the only algorithm defined in AWR/2'
      };
    }
    if (!SRI_SHA256.test(value)) {
      return { ok: false, code: 'AWR-CHAIN-002', detail: where + ' is not base64 of 32 bytes with padding' };
    }
    try {
      if (base64Decode(value.slice(dash + 1)).length !== 32) {
        return { ok: false, code: 'AWR-CHAIN-002', detail: where + ' does not decode to 32 bytes' };
      }
    } catch (e) {
      return { ok: false, code: 'AWR-CHAIN-002', detail: where + ' is not valid base64' };
    }
    return { ok: true };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 6. §5 Issuer identity: did:key and the optional JWK
  // ─────────────────────────────────────────────────────────────────────────

  /** §5.1, the other direction: 32 raw bytes to `did:key:z…`. */
  function didFromPublicKey(publicKey) {
    var payload = new Uint8Array(2 + publicKey.length);
    payload[0] = ED25519_MULTICODEC[0];
    payload[1] = ED25519_MULTICODEC[1];
    payload.set(publicKey, 2);
    return DID_KEY_PREFIX + 'z' + base58btcEncode(payload);
  }

  /**
   * §5.1 `did:key:z<base58btc(0xed 0x01 || publicKey)>`.
   * Returns { did, multibase, publicKey }.
   * Throws AwrError('AWR-KEY-001' | 'AWR-KEY-002').
   */
  function parseDidKey(did) {
    if (typeof did !== 'string' || did.indexOf(DID_KEY_PREFIX) !== 0) {
      throw AwrError('AWR-KEY-001', 'issuer.id ' + JSON.stringify(String(did)) + ' is not a did:key; ' +
        'AWR/2 supports no DID method whose resolution needs the network (§5.1)');
    }
    var mb = did.slice(DID_KEY_PREFIX.length);
    if (mb.charAt(0) !== 'z') {
      throw AwrError('AWR-KEY-002', 'multibase prefix ' + JSON.stringify(mb.charAt(0)) +
        ' is not "z" (base58btc)');
    }
    var bytes = base58btcDecode(mb.slice(1));
    if (bytes.length < 2) {
      throw AwrError('AWR-KEY-002', 'did:key payload is shorter than its multicodec');
    }
    if (bytes[0] !== ED25519_MULTICODEC[0] || bytes[1] !== ED25519_MULTICODEC[1]) {
      // §5.1: a well-formed DID naming a *recognised* other key type is
      // AWR-KEY-004 ("this is a key AWR/2 does not sign with"); an unrecognised
      // or undecodable one is AWR-KEY-002 ("this is corrupt"). Reporting both as
      // KEY-002 loses the difference between a version problem and a transport
      // problem, and the two are diagnosed differently.
      var named = OTHER_KEY_MULTICODECS[toHex(bytes.subarray(0, 2))];
      if (named) {
        throw AwrError('AWR-KEY-004', 'did:key names a ' + named + ' key; AWR/2 defines ' +
          'ed25519-pub (0xed 0x01) only (§5.1)');
      }
      throw AwrError('AWR-KEY-002', 'unrecognised multicodec 0x' + toHex(bytes.subarray(0, 2)) +
        ' in did:key; expected 0xed01 (ed25519-pub)');
    }
    if (bytes.length !== 34) {
      throw AwrError('AWR-KEY-002', 'ed25519-pub multicodec with ' + (bytes.length - 2) +
        ' key bytes, expected 32');
    }
    // Re-encoding must reproduce the same multibase string: a non-canonical
    // base58btc rendering of the same key would otherwise give one key two DIDs,
    // and `verificationMethod` (§5.3) is compared as a string.
    if (base58btcEncode(bytes) !== mb.slice(1)) {
      throw AwrError('AWR-KEY-002', 'base58btc encoding is not canonical');
    }
    return { did: did, multibase: mb, publicKey: bytes.subarray(2) };
  }

  /**
   * §5.2: an `issuer.publicKeyJwk`, if present, MUST be an RFC 8037 OKP/Ed25519
   * JWK whose `x` is exactly the did:key's 32 bytes. A mismatch invalidates the
   * document — two disagreeing statements of the signing key inside one signed
   * document is a downgrade surface, not a redundancy.
   */
  function checkPublicKeyJwk(jwk, publicKey, findings) {
    if (jwk === undefined || jwk === null) return;
    if (typeof jwk !== 'object' || Array.isArray(jwk)) {
      findings.error('AWR-KEY-003', 'issuer.publicKeyJwk is not an object');
      return;
    }
    if (jwk.kty !== 'OKP' || jwk.crv !== 'Ed25519') {
      findings.error('AWR-KEY-004', 'issuer.publicKeyJwk is kty=' + JSON.stringify(jwk.kty) +
        ' crv=' + JSON.stringify(jwk.crv) + '; AWR/2 requires OKP/Ed25519 (RFC 8037)');
      return;
    }
    if (typeof jwk.x !== 'string') {
      findings.error('AWR-KEY-003', 'issuer.publicKeyJwk.x is missing or not a string');
      return;
    }
    var raw;
    try {
      raw = base64Decode(jwk.x);
    } catch (e) {
      findings.error('AWR-KEY-003', 'issuer.publicKeyJwk.x is not base64url');
      return;
    }
    if (raw.length !== 32 || !bytesEqual(raw, publicKey)) {
      findings.error('AWR-KEY-003', 'issuer.publicKeyJwk.x (' + toHex(raw) +
        ') does not equal the key in issuer.id (' + toHex(publicKey) + ')');
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 7. Ed25519 verification
  // ─────────────────────────────────────────────────────────────────────────

  var _webcryptoEd25519 = null;      // null = untested, true/false = known

  function verifyEd25519(publicKey, signature, message, opts) {
    var force = opts && opts.forceEd25519Backend;
    if (force === 'bigint') return Promise.resolve(ed25519VerifyBigInt(publicKey, signature, message));
    if (force === 'nacl') return Promise.resolve(naclVerify(publicKey, signature, message));

    if (_webcryptoEd25519 === false) return fallbackVerify(publicKey, signature, message);
    var s;
    try { s = subtle(); } catch (e) { return fallbackVerify(publicKey, signature, message); }
    return Promise.resolve()
      .then(function () {
        return s.importKey('raw', publicKey, { name: 'Ed25519' }, false, ['verify']);
      })
      .then(function (key) {
        _webcryptoEd25519 = true;
        return s.verify({ name: 'Ed25519' }, key, signature, message);
      })
      .catch(function () {
        // Host has no Ed25519 in WebCrypto (older Safari/Firefox): use a local
        // implementation rather than a network-loaded library.
        _webcryptoEd25519 = false;
        return fallbackVerify(publicKey, signature, message);
      });
  }

  function fallbackVerify(publicKey, signature, message) {
    var n = naclGlobal();
    if (n) return Promise.resolve(naclVerify(publicKey, signature, message));
    return Promise.resolve(ed25519VerifyBigInt(publicKey, signature, message));
  }

  function naclGlobal() {
    var n = (typeof root !== 'undefined' && root.nacl) ? root.nacl : (typeof nacl !== 'undefined' ? nacl : null);
    return (n && n.sign && n.sign.detached && n.sign.detached.verify) ? n : null;
  }

  function naclVerify(publicKey, signature, message) {
    var n = naclGlobal();
    if (!n) return false;
    try { return n.sign.detached.verify(message, signature, publicKey); } catch (e) { return false; }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 8. §3.1 envelope, §3.3–3.5 subjects
  // ─────────────────────────────────────────────────────────────────────────

  function isPlainObject(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

  function parseInstant(value) {
    if (typeof value !== 'string' || !RFC3339_UTC.test(value)) return NaN;
    return Date.parse(value);
  }

  function checkEnvelope(doc, findings) {
    var ctx = doc['@context'];
    if (!Array.isArray(ctx) || ctx.length === 0 || ctx[0] !== VC2_CONTEXT) {
      findings.error('AWR-DOC-002', '@context must be an array whose first element is exactly ' + VC2_CONTEXT);
    }
    if (!Array.isArray(ctx) || ctx.indexOf(AWR2_CONTEXT) < 0) {
      findings.error('AWR-DOC-003', '@context does not contain ' + AWR2_CONTEXT);
    }

    var type = doc.type;
    if (!Array.isArray(type) || type.indexOf('VerifiableCredential') < 0) {
      findings.error('AWR-DOC-004', 'type must be an array containing "VerifiableCredential"');
    }
    // §3.1: `type` is a set. A repeated member makes a reader that takes the first match
    // and a reader that counts matches disagree about the same bytes, so it is rejected
    // rather than de-duplicated — which is what this verifier did before.
    if (Array.isArray(type)) {
      var seenType = Object.create(null), repeatedType = [];
      for (var ti = 0; ti < type.length; ti++) {
        var tk = typeof type[ti] === 'string' ? type[ti] : JSON.stringify(type[ti]);
        if (seenType[tk] && repeatedType.indexOf(tk) < 0) repeatedType.push(tk);
        seenType[tk] = true;
      }
      if (repeatedType.length) {
        findings.error('AWR-DOC-005',
          'type is a set and must not repeat a value; repeated: ' + repeatedType.join(', '));
      }
    }

    var found = [];
    if (Array.isArray(type)) {
      for (var i = 0; i < AWR_TYPES.length; i++) if (type.indexOf(AWR_TYPES[i]) >= 0) found.push(AWR_TYPES[i]);
    }
    if (found.length !== 1) {
      findings.error('AWR-DOC-005', found.length === 0
        ? 'type contains no AWR document type (WorkReceipt / VerificationVerdict / BlameAttestation)'
        : 'type contains more than one AWR document type: ' + found.join(', '));
    }

    if (typeof doc.id !== 'string' || !ABSOLUTE_URI.test(doc.id)) {
      findings.error('AWR-DOC-006', 'id is missing or not an absolute URI');
    }

    if (typeof doc.issuer === 'string') {
      findings.error('AWR-DOC-010', 'issuer is a bare string; AWR/2 requires an object with id (§3.1)');
    } else if (!isPlainObject(doc.issuer) || typeof doc.issuer.id !== 'string') {
      findings.error('AWR-DOC-010', 'issuer is missing, not an object, or has no id');
    }

    var vf = parseInstant(doc.validFrom);
    if (isNaN(vf)) {
      findings.error('AWR-DOC-007', 'validFrom is missing or is not an RFC 3339 UTC date-time with a Z offset');
    } else if (doc.validUntil !== undefined) {
      var vu = parseInstant(doc.validUntil);
      if (isNaN(vu)) findings.error('AWR-DOC-007', 'validUntil is not an RFC 3339 UTC date-time with a Z offset');
      else if (vu <= vf) findings.error('AWR-DOC-007', 'validUntil is not later than validFrom');
    }

    if (typeof doc.awrVersion !== 'string' || !/^\d+\.\d+\.\d+$/.test(doc.awrVersion)) {
      findings.error('AWR-DOC-009', 'awrVersion is missing or malformed (expected "2.0.0")');
    } else if (doc.awrVersion.split('.')[0] !== '2') {
      findings.error('AWR-DOC-009', 'awrVersion major ' + doc.awrVersion.split('.')[0] +
        ' is not implemented by this verifier');
    }

    if (!isPlainObject(doc.credentialSubject)) {
      findings.error('AWR-DOC-008', 'credentialSubject is missing or is not a single object');
    }

    return found.length === 1 ? found[0] : null;
  }

  function checkTimeWarnings(doc, findings, o) {
    var vf = parseInstant(doc.validFrom);
    if (!isNaN(vf) && vf > o.now + o.clockSkewSeconds * 1000) {
      findings.warn('AWR-TIME-001', 'validFrom (' + doc.validFrom + ') is in the future beyond the ' +
        o.clockSkewSeconds + 's skew allowance');
    }
    if (doc.validUntil !== undefined) {
      var vu = parseInstant(doc.validUntil);
      if (!isNaN(vu) && vu < o.now) {
        findings.warn('AWR-TIME-002', 'validUntil (' + doc.validUntil + ') is in the past');
      }
    }
    // §11.3: age is policy, never validity. Only surfaced when the caller asks
    // for an age policy, and only ever as a warning.
    if (o.maxAgeDays != null && !isNaN(vf)) {
      var ageDays = (o.now - vf) / 86400000;
      if (ageDays > o.maxAgeDays) {
        findings.warn('AWR-TIME-002', 'document is ' + Math.floor(ageDays) + ' days old, beyond the ' +
          'caller\'s ' + o.maxAgeDays + '-day policy window; age is not a validity property (§11.3)');
      }
    }
  }

  function checkDigestReference(ref, where, findings, opts) {
    if (!isPlainObject(ref)) {
      findings.error('AWR-CHAIN-002', where + ' is not a digest-reference object');
      return false;
    }
    if (ref.digestSRI === undefined) {
      findings.error('AWR-CHAIN-001', where + ' has no digestSRI');
      return false;
    }
    var r = checkSri(ref.digestSRI, where + '.digestSRI');
    if (!r.ok) { findings.error(r.code, r.detail); return false; }
    return true;
  }

  function checkWorkReceipt(subject, findings, opts) {
    var work = subject.work;
    if (!isPlainObject(work)) {
      findings.error('AWR-RCPT-005', 'credentialSubject.work is missing or not an object');
      findings.error('AWR-RCPT-003', 'credentialSubject.work is missing, so work.completedAt is absent');
      findings.error('AWR-RCPT-006', 'credentialSubject.work is missing, so work.status is absent');
    } else {
      if (typeof work.modelId !== 'string' || work.modelId.length === 0) {
        findings.error('AWR-RCPT-005', 'work.modelId is missing or empty');
      }
      if (WORK_STATUS.indexOf(work.status) < 0) {
        findings.error('AWR-RCPT-006', 'work.status ' + JSON.stringify(work.status) +
          ' is not one of ' + WORK_STATUS.join(', '));
      }
      var completed = parseInstant(work.completedAt);
      if (isNaN(completed)) {
        findings.error('AWR-RCPT-003', 'work.completedAt is missing or not an RFC 3339 UTC date-time');
      } else if (work.startedAt !== undefined) {
        var started = parseInstant(work.startedAt);
        if (isNaN(started)) findings.error('AWR-RCPT-003', 'work.startedAt is not an RFC 3339 UTC date-time');
        else if (completed < started) findings.error('AWR-RCPT-003', 'work.completedAt is earlier than work.startedAt');
      }
      if (work.latencyMs !== undefined) {
        if (typeof work.latencyMs !== 'number' || !Number.isInteger(work.latencyMs) || work.latencyMs < 0) {
          findings.error('AWR-RCPT-004', 'work.latencyMs must be a non-negative integer, got ' +
            JSON.stringify(work.latencyMs));
        }
      }
    }

    ['inputDigest', 'outputDigest'].forEach(function (field) {
      var v = subject[field];
      if (v === undefined) {
        findings.error('AWR-RCPT-001', field + ' is missing');
        return;
      }
      var r = checkSri(v, field);
      if (!r.ok) findings.error('AWR-RCPT-001', r.detail);
    });

    if (subject.price !== undefined) {
      var p = subject.price;
      if (!isPlainObject(p)) {
        findings.error('AWR-RCPT-002', 'price is not an object');
      } else {
        if (typeof p.currency !== 'string' || !(ISO4217.test(p.currency) || p.currency.indexOf('urn:') === 0)) {
          findings.error('AWR-RCPT-002', 'price.currency ' + JSON.stringify(p.currency) +
            ' is neither an ISO 4217 alphabetic code nor a urn: URI');
        }
        if (typeof p.amount === 'number') {
          findings.error('AWR-RCPT-002', 'price.amount is a JSON number; §4.3 requires a decimal string');
        } else if (typeof p.amount !== 'string' || !DECIMAL_STRING.test(p.amount)) {
          findings.error('AWR-RCPT-002', 'price.amount ' + JSON.stringify(p.amount) +
            ' is not a decimal string matching ^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$');
        }
      }
    }

    if (subject.parents !== undefined) {
      if (!Array.isArray(subject.parents)) {
        findings.error('AWR-CHAIN-002', 'parents is present but not an array');
      } else {
        var byId = Object.create(null);
        subject.parents.forEach(function (ref, i) {
          var where = 'parents[' + i + ']';
          if (!checkDigestReference(ref, where, findings, opts)) return;
          if (typeof ref.id === 'string') {
            if (byId[ref.id] !== undefined && byId[ref.id] !== ref.digestSRI) {
              findings.error('AWR-CHAIN-006', 'parents contains id ' + ref.id +
                ' twice with conflicting digests — one of the two is forged');
            }
            byId[ref.id] = ref.digestSRI;
          }
        });
      }
    }

    // §10.3: an accountability binding is checked for being present,
    // well-formed and signed — never against a chain or an RPC endpoint.
    if (subject.settlement !== undefined) {
      if (!isPlainObject(subject.settlement)) {
        findings.error('AWR-PROFILE-004', 'settlement is present but is not an object');
      } else {
        findings.warn('AWR-L2-001', 'settlement binding is present and well-formed but on-chain existence ' +
          'was NOT checked; a verifier must not contact a chain, an RPC endpoint or any other network ' +
          'service (§10.3)');
      }
    }

    // §7.3: opaque. Present-and-unverified is the honest report.
    if (isPlainObject(subject.environment)) {
      ['teeAttestation', 'zkProof'].forEach(function (k) {
        if (subject.environment[k] !== undefined) {
          findings.warn('AWR-ENV-001', 'environment.' + k + ' is present and was NOT verified: ' +
            'AWR/2 treats it as an opaque object, and checking it needs the platform\'s certificate ' +
            'chain, which is a network- and vendor-dependent operation (§7.3)');
        }
      });
    }
  }

  function checkUnitDecimal(value, field, code, findings) {
    if (value === undefined) return;
    if (typeof value === 'number') {
      findings.error(code, field + ' is a JSON number; §4.3 requires a decimal string');
      return;
    }
    if (typeof value !== 'string' || !UNIT_DECIMAL_STRING.test(value)) {
      findings.error(code, field + ' ' + JSON.stringify(value) + ' is not a decimal string in [0,1]');
    }
  }

  function checkVerdict(subject, findings, opts) {
    if (!isPlainObject(subject.verifiedWork)) {
      findings.error('AWR-VDCT-001', 'verifiedWork is missing or not an object');
    } else {
      if (typeof subject.verifiedWork.id !== 'string' || subject.verifiedWork.id.length === 0) {
        findings.error('AWR-VDCT-001', 'verifiedWork.id is missing (§3.4 requires both id and digestSRI)');
      }
      if (subject.verifiedWork.digestSRI === undefined) {
        findings.error('AWR-VDCT-001', 'verifiedWork.digestSRI is missing');
      } else {
        var r = checkSri(subject.verifiedWork.digestSRI, 'verifiedWork.digestSRI');
        if (!r.ok) findings.error(r.code, r.detail);
      }
    }
    if (VERDICTS.indexOf(subject.verdict) < 0) {
      findings.error('AWR-VDCT-004', 'verdict ' + JSON.stringify(subject.verdict) +
        ' is not one of pass, fail, inconclusive');
    }
    checkUnitDecimal(subject.score, 'score', 'AWR-VDCT-002', findings);
    if (!isPlainObject(subject.method) || typeof subject.method.id !== 'string' || subject.method.id.length === 0) {
      findings.error('AWR-VDCT-003', 'method is missing or method.id is empty');
    }
    if (isPlainObject(subject.policy)) {
      checkUnitDecimal(subject.policy.threshold, 'policy.threshold', 'AWR-VDCT-002', findings);
    }
    if (subject.evidence !== undefined) {
      if (!Array.isArray(subject.evidence)) {
        findings.error('AWR-VDCT-007', 'evidence is present but not an array');
      } else {
        subject.evidence.forEach(function (ev, i) {
          if (!isPlainObject(ev) || ev.digestSRI === undefined) {
            findings.error('AWR-VDCT-007', 'evidence[' + i + '] has no digestSRI');
            return;
          }
          var r = checkSri(ev.digestSRI, 'evidence[' + i + '].digestSRI');
          if (!r.ok) findings.error(r.code, r.detail);
        });
      }
    }
    // §3.4: the stated verdict is authoritative, but disagreement with
    // score/threshold is evidence in itself → warning, decimal comparison.
    if (typeof subject.score === 'string' && UNIT_DECIMAL_STRING.test(subject.score) &&
        isPlainObject(subject.policy) && typeof subject.policy.threshold === 'string' &&
        UNIT_DECIMAL_STRING.test(subject.policy.threshold) &&
        VERDICTS.indexOf(subject.verdict) >= 0) {
      var cmp = decimalCompare(subject.score, subject.policy.threshold);
      if (subject.verdict === 'pass' && cmp < 0) {
        findings.warn('AWR-VDCT-006', 'verdict "pass" but score ' + subject.score +
          ' is below policy.threshold ' + subject.policy.threshold);
      } else if (subject.verdict === 'fail' && cmp >= 0) {
        findings.warn('AWR-VDCT-006', 'verdict "fail" but score ' + subject.score +
          ' meets policy.threshold ' + subject.policy.threshold);
      }
    }
    if (subject.stake !== undefined) {
      findings.warn('AWR-L2-001', 'stake binding is present but on-chain existence was NOT checked: ' +
        'a verifier must not contact a chain or RPC endpoint (§10.3)');
    }
  }

  function checkBlame(subject, findings, opts) {
    ['chain', 'blamedWork'].forEach(function (field) {
      if (!isPlainObject(subject[field])) {
        findings.error('AWR-BLAME-003', field + ' is missing or not a digest reference');
        return;
      }
      if (subject[field].digestSRI === undefined) {
        findings.error('AWR-BLAME-003', field + '.digestSRI is missing');
        return;
      }
      var r = checkSri(subject[field].digestSRI, field + '.digestSRI');
      if (!r.ok) findings.error('AWR-BLAME-003', r.detail);
    });
    if (FAILURE_CLASSES.indexOf(subject.failureClass) < 0) {
      findings.error('AWR-BLAME-002', 'failureClass ' + JSON.stringify(subject.failureClass) +
        ' is not one of ' + FAILURE_CLASSES.join(', '));
    }
    checkUnitDecimal(subject.confidence, 'confidence', 'AWR-BLAME-004', findings);
    if (!isPlainObject(subject.method) || typeof subject.method.id !== 'string' || subject.method.id.length === 0) {
      findings.error('AWR-VDCT-003', 'method is missing or method.id is empty');
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 9. §6 proof verification
  // ─────────────────────────────────────────────────────────────────────────

  function checkProofConfig(proof, doc, issuerDid, multibase, findings) {
    var ok = true;
    if (proof.type !== PROOF_TYPE) {
      findings.error('AWR-PROOF-002', 'proof.type ' + JSON.stringify(proof.type) + ' is not ' + PROOF_TYPE);
      ok = false;
    }
    if (proof.cryptosuite !== CRYPTOSUITE) {
      findings.error('AWR-PROOF-003', 'cryptosuite ' + JSON.stringify(proof.cryptosuite) +
        ' is unsupported; AWR/2 registers exactly one value, ' + CRYPTOSUITE +
        ' — an unknown suite is rejected, never skipped (§6.4)');
      ok = false;
    }
    if (proof.proofPurpose !== 'assertionMethod') {
      findings.error('AWR-PROOF-004', 'proofPurpose ' + JSON.stringify(proof.proofPurpose) +
        ' is not assertionMethod');
      ok = false;
    }
    if (isNaN(parseInstant(proof.created))) {
      findings.error('AWR-PROOF-009', 'proof.created is missing or not an RFC 3339 UTC date-time');
      ok = false;
    }
    if (issuerDid && proof.verificationMethod !== issuerDid + '#' + multibase) {
      findings.error('AWR-PROOF-007', 'verificationMethod ' + JSON.stringify(proof.verificationMethod) +
        ' is not <issuer.id>#<method-specific-id> (' + issuerDid + '#' + multibase + ')');
      ok = false;
    }
    if (proof['@context'] !== undefined && doc['@context'] !== undefined) {
      var a, b;
      try { a = jcsCanonicalize(proof['@context']); b = jcsCanonicalize(doc['@context']); } catch (e) { a = 1; b = 2; }
      if (a !== b) {
        findings.error('AWR-PROOF-008', 'proof.@context differs from the document @context');
        ok = false;
      }
    }
    return ok;
  }

  function decodeProofValue(proofValue, findings) {
    if (typeof proofValue !== 'string' || proofValue.length === 0) {
      findings.error('AWR-PROOF-005', 'proofValue is missing or not a string');
      return null;
    }
    if (proofValue.charAt(0) !== 'z') {
      findings.error('AWR-PROOF-005', 'proofValue does not start with the base58btc multibase prefix "z"' +
        ' — base64, hex and unprefixed values are rejected, including the AWR/1 legacy form (§6.1, §12)');
      return null;
    }
    var sig;
    try {
      sig = base58btcDecode(proofValue.slice(1));
    } catch (e) {
      findings.error('AWR-PROOF-005', 'proofValue is not valid base58btc: ' + (e.detail || e.message));
      return null;
    }
    if (sig.length !== 64) {
      findings.error('AWR-PROOF-005', 'proofValue decodes to ' + sig.length + ' bytes; expected exactly 64');
      return null;
    }
    return sig;
  }

  /**
   * §6.2 steps 2–6 / §6.3 step 5. Returns
   * { proofConfigHash, transformedDocumentHash, hashData } as byte arrays.
   */
  function computeHashData(doc, proof, opts) {
    var unsecured = {};
    Object.keys(doc).forEach(function (k) { if (k !== 'proof') unsecured[k] = doc[k]; });

    var config = {};
    Object.keys(proof).forEach(function (k) { if (k !== 'proofValue') config[k] = proof[k]; });
    // §6.2 step 1: the proof config carries the document's @context. §6.2 step 9 makes
    // an issuer emit that same value in the proof, so for a document issued after that
    // rule landed this assignment overwrites an identical value; it stays because §6.3
    // step 4 requires a verifier to accept a proof that omits it — every AWR/2 document
    // issued before the rule does — and because AWR-PROOF-008 has already established
    // that any @context the proof does carry equals this one.
    if (doc['@context'] !== undefined) config['@context'] = doc['@context'];

    var canonicalProofConfig, transformedDocument;
    try {
      canonicalProofConfig = jcsCanonicalizeBytes(config, opts);
      transformedDocument = jcsCanonicalizeBytes(unsecured, opts);
    } catch (e) {
      return Promise.reject(e);
    }

    return Promise.all([sha256(canonicalProofConfig), sha256(transformedDocument)])
      .then(function (h) {
        return {
          canonicalProofConfig: canonicalProofConfig,
          transformedDocument: transformedDocument,
          proofConfigHash: h[0],
          transformedDocumentHash: h[1],
          // §6.2 step 6: proof config FIRST. This order is normative and is the
          // most frequent interoperability error in Data Integrity code.
          hashData: concatBytes(h[0], h[1])
        };
      });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 10. §8 chain resolution over caller-supplied documents only
  // ─────────────────────────────────────────────────────────────────────────

  function resolveChain(subjectDoc, pool, findings, o) {
    // `pool` is an array of { doc, sri, type }.
    var byDigest = Object.create(null), byId = Object.create(null);
    pool.forEach(function (entry) {
      byDigest[entry.sri] = entry;
      if (typeof entry.doc.id === 'string') {
        (byId[entry.doc.id] || (byId[entry.doc.id] = [])).push(entry);
      }
    });

    var resolved = 0, unresolved = 0, nodes = 0, maxDepth = 0;
    var edges = [];
    var limitReported = false;
    var onPath = Object.create(null);
    var visited = Object.create(null);
    // §8.2: the same parent `id` claimed with different digests, collected over
    // EVERY edge the resolution observes — not only within one `parents` array.
    // Two receipts naming one parent id with two digests is the same statement
    // that one of them is forged, and the more interesting one, because it means
    // the conflict survived a hop.
    var digestsById = Object.create(null);

    // §8.2: cycle detection keys on document `id`. A cycle in the digests is not
    // constructible — an edge commits to the parent's exact bytes (§8.1), so it
    // would be a SHA-256 fixed point — so the only cycle that exists runs through
    // identifiers, which is the field an attacker controls.
    function keyOf(entry) {
      return typeof entry.doc.id === 'string' && entry.doc.id ? 'id:' + entry.doc.id : 'sri:' + entry.sri;
    }

    function walk(entry, depth) {
      if (depth > o.chainMaxDepth || nodes > o.chainMaxNodes) {
        if (!limitReported) {
          limitReported = true;
          findings.error('AWR-CHAIN-005', 'chain resolution exceeded the configured limits (depth ' +
            o.chainMaxDepth + ', nodes ' + o.chainMaxNodes + '); an unbounded walk over ' +
            'attacker-influenced input is a denial of service (§8.2)');
        }
        return;
      }
      if (depth > maxDepth) maxDepth = depth;
      var key = keyOf(entry);
      if (onPath[key]) {
        findings.error('AWR-CHAIN-004', 'cycle detected: ' + key.slice(key.indexOf(':') + 1) +
          ' is its own ancestor on the resolution path (§8.2)');
        return;
      }
      if (visited[key]) return;
      onPath[key] = true;
      nodes++;

      var parents = (isPlainObject(entry.doc.credentialSubject) && entry.doc.credentialSubject.parents) || [];
      if (Array.isArray(parents)) {
        parents.forEach(function (ref, i) {
          if (!isPlainObject(ref) || typeof ref.digestSRI !== 'string') return;   // already reported
          // §11.1: an entry that is not a well-formed digest reference (§3.2) is
          // reported through AWR-CHAIN-001/002 and counted in NEITHER total — it
          // never entered resolution, so calling it `unresolved` would conflate
          // "I could not find this parent" with "this edge names no parent I could
          // look for". A `sha512-` edge is a string, so it used to slip past the
          // guard above and be counted as one unresolved edge here.
          if (!checkSri(ref.digestSRI, 'parents[' + i + '].digestSRI').ok) return;
          if (typeof ref.id === 'string' && ref.id) {
            var seen = digestsById[ref.id] || (digestsById[ref.id] = []);
            if (seen.indexOf(ref.digestSRI) < 0) seen.push(ref.digestSRI);
          }
          var target = byDigest[ref.digestSRI];
          var edgeResolved = !!target;
          if (!target) {
            // §8.2: no supplied document has the committed digest. If one carries
            // the referenced id, report AWR-CHAIN-003, count the edge unresolved —
            // nothing the child signed has been confirmed — and still walk through
            // it, so that a cycle or a conflict behind a broken edge is found.
            // Without that last part AWR-CHAIN-004 is unreachable.
            var sameId = (ref.id && byId[ref.id]) || [];
            if (sameId.length > 0) {
              findings.error('AWR-CHAIN-003', 'supplied document ' + ref.id + ' has digest ' +
                sameId[0].sri + ' but parents[' + i + '] commits to ' + ref.digestSRI);
              target = sameId[0];
            }
          }
          edges.push({ child: entry.sri, parent: ref.digestSRI, id: ref.id || null,
                       role: ref.role || null, resolved: edgeResolved });
          if (edgeResolved) resolved++; else unresolved++;
          if (!target) return;
          if (edgeResolved) {
            // §8.3: binding input to output across a hop.
            var ps = isPlainObject(target.doc.credentialSubject) ? target.doc.credentialSubject : {};
            var cs = isPlainObject(entry.doc.credentialSubject) ? entry.doc.credentialSubject : {};
            if (typeof ps.outputDigest === 'string' && typeof cs.inputDigest === 'string' &&
                ps.outputDigest !== cs.inputDigest) {
              findings.warn('AWR-CHAIN-007', 'parent outputDigest differs from child inputDigest for edge ' +
                (ref.id || ref.digestSRI) + '; a legitimate hop often transforms its input, so this is not ' +
                'invalidity (§8.3)');
            }
          }
          walk(target, depth + 1);
        });
      }
      onPath[key] = false;
      visited[key] = true;
    }

    var start = null;
    for (var i = 0; i < pool.length; i++) if (pool[i].doc === subjectDoc) start = pool[i];
    if (start) walk(start, 0);

    Object.keys(digestsById).forEach(function (id) {
      if (digestsById[id].length > 1) {
        findings.error('AWR-CHAIN-006', 'parent id ' + id + ' is referenced with ' +
          digestsById[id].length + ' conflicting digests across the resolved chain; one of them is ' +
          'forged (§8.2)');
      }
    });

    return { resolved: resolved, unresolved: unresolved, depth: maxDepth, nodes: nodes, edges: edges };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 11. §10 profiles
  // ─────────────────────────────────────────────────────────────────────────

  function evaluateProfiles(receiptEntry, pool, findings, o) {
    // A profile is never granted by self-assertion (§3.3, §10). Higher levels are
    // still *evaluated* when the caller named none, so that §10.4's "highest
    // profile satisfied" can be reported — but no AWR-PROFILE-* code is emitted
    // for a level nobody asked about (§10.4). Those codes carry severity `error`
    // (§11.2) and a code has exactly one severity (§11.1), so the alternatives
    // are both wrong: reporting them as errors makes every plain L0 receipt
    // invalid, and re-emitting them at warning severity makes the result
    // incomparable with any other implementation's.
    var requested = o.profile || null;
    var report = function (code, detail) {
      if (requested) findings.error(code, detail);
    };

    var evaluated = { L0: true, L1: false, L2: false };
    var receiptSri = receiptEntry.sri;
    var receiptIssuer = (isPlainObject(receiptEntry.doc.issuer) && receiptEntry.doc.issuer.id) || null;

    var verdicts = pool.filter(function (e) {
      return e.type === 'VerificationVerdict' && e.valid &&
             isPlainObject(e.doc.credentialSubject) &&
             isPlainObject(e.doc.credentialSubject.verifiedWork) &&
             e.doc.credentialSubject.verifiedWork.digestSRI === receiptSri;
    });

    var independent = verdicts.filter(function (e) {
      return isPlainObject(e.doc.issuer) && e.doc.issuer.id !== receiptIssuer;
    });
    var selfIssued = verdicts.length - independent.length;

    if (requested === 'L0') return { profile: 'L0', evaluated: evaluated };

    if (independent.length === 0) {
      if (verdicts.length > 0 && selfIssued > 0) {
        report('AWR-PROFILE-002', 'the only verdict(s) for this receipt were issued by the receipt\'s own ' +
          'issuer (' + receiptIssuer + '); self-verification is the failure mode L1 exists to exclude (§10.2)');
      } else {
        report('AWR-PROFILE-001', 'no valid VerificationVerdict for this receipt was supplied; L1 requires ' +
          'one, and a verifier may not fetch it (§13.5)');
      }
      return { profile: 'L0', evaluated: evaluated };
    }
    evaluated.L1 = true;
    evaluated.selfIssuedVerdicts = selfIssued;      // non-normative detail, not a code
    if (requested === 'L1') return { profile: 'L1', evaluated: evaluated };

    var issuers = Object.create(null), distinct = 0;
    independent.forEach(function (e) {
      var id = e.doc.issuer.id;
      if (!issuers[id]) { issuers[id] = true; distinct++; }
    });
    var l2 = true;
    if (distinct < 2) {
      report('AWR-PROFILE-003', 'L2 requires at least two valid verdicts from distinct issuers; found ' + distinct);
      l2 = false;
    }
    var subject = isPlainObject(receiptEntry.doc.credentialSubject) ? receiptEntry.doc.credentialSubject : {};
    var hasSettlement = isPlainObject(subject.settlement);
    var stakedVerdicts = independent.filter(function (e) {
      return isPlainObject(e.doc.credentialSubject) && isPlainObject(e.doc.credentialSubject.stake);
    });
    var allStaked = independent.length > 0 && stakedVerdicts.length === independent.length;
    if (!hasSettlement && !allStaked) {
      report('AWR-PROFILE-004', 'L2 requires an accountability binding: the receipt carries settlement, ' +
        'or each verdict carries stake, or both');
      l2 = false;
    }
    if (l2) { evaluated.L2 = true; return { profile: 'L2', evaluated: evaluated }; }
    return { profile: 'L1', evaluated: evaluated };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 12. §12 AWR/1 legacy
  // ─────────────────────────────────────────────────────────────────────────
  //
  // AWR/1 signed a pipe-delimited rendering of `credentialSubject` ONLY, with
  // NFC-normalized strings and keys sorted by code point. Both deviate from
  // RFC 8785 and belong to the legacy dialect definition, not to AWR/2 (§12).
  //
  // Two dialects exist because the reference issuer distinguished integers from
  // floats and the reference verifier did not:
  //   dialect A (integer-preserving): a JSON integer renders as `2340`
  //   dialect B (float-coercing):     the same integer renders as `2340.0`
  // Either is accepted for legacy documents; failure under both is
  // AWR-LEGACY-002.

  /** Code-point order, which is what the legacy Python issuer's sorted() used. */
  function codePointCompare(a, b) {
    var ap = Array.from(a), bp = Array.from(b);
    var n = Math.min(ap.length, bp.length);
    for (var i = 0; i < n; i++) {
      var x = ap[i].codePointAt(0), y = bp[i].codePointAt(0);
      if (x !== y) return x < y ? -1 : 1;
    }
    return ap.length === bp.length ? 0 : (ap.length < bp.length ? -1 : 1);
  }

  /** §12.1 leaf rendering. Throws when the value is outside the defined range. */
  function legacyLeaf(val, dialect) {
    if (val === null) return 'null';
    if (val === true) return 'true';
    if (val === false) return 'false';
    if (typeof val === 'string') return val.normalize ? val.normalize('NFC') : val;
    if (typeof val === 'number') {
      // §12.1: the rendering is defined only below 10^15, so no implementation
      // has to reproduce another language's float printing. Outside it the
      // legacy form does not exist and the caller reports AWR-LEGACY-002.
      if (!isFinite(val) || Math.abs(val) >= 1e15) {
        throw AwrError('AWR-LEGACY-002', 'number ' + val + ' is outside the range in which the ' +
          'AWR/1 rendering is defined (|x| < 10^15, §12.1)');
      }
      if (Number.isInteger(val)) return dialect === 'B' ? String(val) + '.0' : String(val);
      return val.toFixed(10);          // ten fractional digits, zeros KEPT
    }
    // Reached only for an empty object or array, which `legacyWalk` routes here.
    if (typeof val === 'object') return '';
    throw AwrError('AWR-LEGACY-002', 'unrenderable AWR/1 leaf of type ' + typeof val);
  }

  /**
   * §12.1: the leaves of `credentialSubject` as `path=leaf` entries joined by
   * `|`, paths dot-separated with array indices as segments, entries sorted by
   * path in code-point order, strings NFC-normalized and unquoted.
   *
   * This is a *description of AWR/1*, written down in §12.1 because the earlier
   * text ("a pipe-delimited rendering") was not enough to verify one document:
   * this file previously implemented `key:value` pairs with JSON-quoted nested
   * blobs and Python-style `True`/`None`, and therefore verified no receipt any
   * other implementation could produce. Nothing here applies to AWR/2.
   */
  function legacyPipeCanonical(subject, dialect) {
    var entries = [];
    legacyWalk(subject, '', dialect, entries);
    entries.sort(function (a, b) { return codePointCompare(a.path, b.path); });
    return entries.map(function (e) { return e.path + '=' + e.leaf; }).join('|');
  }

  function legacyWalk(val, path, dialect, out) {
    var join = function (p, seg) { return p === '' ? seg : p + '.' + seg; };
    if (Array.isArray(val)) {
      if (val.length === 0) return;                 // §12.1(2): no leaves, no entry
      for (var i = 0; i < val.length; i++) legacyWalk(val[i], join(path, String(i)), dialect, out);
      return;
    }
    if (val !== null && typeof val === 'object') {
      var keys = Object.keys(val).sort(codePointCompare);
      if (keys.length === 0) return;                // §12.1(2)
      for (var k = 0; k < keys.length; k++) {
        var name = keys[k].normalize ? keys[k].normalize('NFC') : keys[k];
        legacyWalk(val[keys[k]], join(path, name), dialect, out);
      }
      return;
    }
    out.push({ path: path, leaf: legacyLeaf(val, dialect) });
  }

  // §12.3 signal 2. Either URI is an AWR/2 claim: the VC 2.0 context postdates
  // AWR/1 (VC 1.1) and the AWR namespace names this specification.
  var AWR2_CONTEXT_URIS = [
    'https://www.w3.org/ns/credentials/v2',
    'https://verify.modelmarket.dev/ns/awr/v2'
  ];
  // §12.3 signals 4 and 5. `credentialSubject.parents` is deliberately absent:
  // Appendix D records that AWR/1 carried `parents` too, as identifier strings,
  // so it is not an AWR/2 claim.
  var AWR2_ENVELOPE_MEMBERS = ['validFrom', 'validUntil'];
  var AWR2_SUBJECT_MEMBERS = ['settlement'];

  /**
   * Every proof object, whether `proof` is one object or an array (§12.3).
   * Position must not matter: reading `proof[0]` let an attacker pick the rule
   * set by ordering the array, and the three implementations then disagreed
   * about the same bytes.
   */
  function proofObjects(doc) {
    if (!isPlainObject(doc)) return [];
    if (Array.isArray(doc.proof)) return doc.proof.filter(isPlainObject);
    return isPlainObject(doc.proof) ? [doc.proof] : [];
  }

  /**
   * The §12.3 AWR/2 signals the document carries. The list is CLOSED: a signal
   * one verifier honours and another ignores is a document the two disagree
   * about. In particular there is no content heuristic here — an earlier
   * revision of this file routed a document to the legacy path when its subject
   * carried `inputHash`/`outputHash`, with no legacy proof in sight, and a
   * heuristic is a signal an attacker can raise at will.
   */
  function awr2Signals(doc) {
    var out = [];
    if (!isPlainObject(doc)) return out;
    if (Object.prototype.hasOwnProperty.call(doc, 'awrVersion')) out.push('awrVersion');
    var ctx = doc['@context'];
    var values = Array.isArray(ctx) ? ctx : [ctx];
    if (values.some(function (v) { return AWR2_CONTEXT_URIS.indexOf(v) !== -1; })) {
      out.push('the AWR/2 @context');
    }
    if (proofObjects(doc).some(function (p) { return p.type === PROOF_TYPE; })) {
      out.push('proof.type DataIntegrityProof');
    }
    AWR2_ENVELOPE_MEMBERS.forEach(function (m) {
      if (Object.prototype.hasOwnProperty.call(doc, m)) out.push(m);
    });
    var s = doc.credentialSubject;
    if (isPlainObject(s)) {
      AWR2_SUBJECT_MEMBERS.forEach(function (m) {
        if (Object.prototype.hasOwnProperty.call(s, m)) out.push('credentialSubject.' + m);
      });
    }
    return out;
  }

  function hasAwr1Proof(doc) {
    return proofObjects(doc).some(function (p) { return p.type === LEGACY_PROOF_TYPE; });
  }

  /**
   * The §12.3 version gate: 'awr2' | 'awr1' | 'disagree', decided before any
   * verification runs. Selecting the legacy path on `proof.type` alone was an
   * unauthenticated forgery path: AWR/1 signs neither `proof.type` nor `issuer`,
   * so a document carrying `awrVersion: "2.0.0"` and a victim's DID was verified
   * under AWR/1 rules against a key the attacker supplied beside it.
   */
  function classifyVersion(doc) {
    var awr1 = hasAwr1Proof(doc);
    var awr2 = awr2Signals(doc).length > 0;
    if (awr1 && awr2) return 'disagree';
    return awr1 ? 'awr1' : 'awr2';
  }

  /** True when the document is to be verified under §12 — and only then. */
  function looksLegacy(doc) {
    return classifyVersion(doc) === 'awr1';
  }

  /**
   * The key `issuer.id` names, or null when it names none (§12.4).
   * A `did:key` bearing a `#` fragment — the §5.3 `verificationMethod` string —
   * names the same key as the bare DID and MUST be read as such: parsing only the
   * bare form let an attacker keep the victim's DID as a literal prefix of
   * `issuer.id` while supplying their own `publicKeyJwk`.
   */
  function issuerIdKey(issuer) {
    if (!isPlainObject(issuer) || typeof issuer.id !== 'string') return null;
    if (issuer.id.indexOf('did:key:') !== 0) return null;
    try { return parseDidKey(issuer.id.split('#')[0]).publicKey; } catch (e) { return null; }
  }

  function sameKey(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) { if (a[i] !== b[i]) return false; }
    return true;
  }

  /** §12.2, in order: publicKeyJwk, publicKeyBase64, a genuine did:key issuer.id. */
  function legacyPublicKey(issuer) {
    if (!isPlainObject(issuer)) return null;
    var jwk = issuer.publicKeyJwk;
    if (isPlainObject(jwk) && jwk.kty === 'OKP' && jwk.crv === 'Ed25519' && typeof jwk.x === 'string') {
      try {
        var raw = base64Decode(jwk.x);
        if (raw.length === 32) return raw;
      } catch (e) { /* fall through to the next source */ }
    }
    if (typeof issuer.publicKeyBase64 === 'string') {
      try {
        var b = base64Decode(issuer.publicKeyBase64);
        if (b.length === 32) return b;
      } catch (e) { /* fall through */ }
    }
    if (typeof issuer.id === 'string') {
      try { return parseDidKey(issuer.id).publicKey; } catch (e) { return null; }
    }
    return null;
  }

  function verifyLegacy(doc, o) {
    var findings = new Findings();
    var checks = [];
    findings.warn('AWR-LEGACY-001', 'verified under the AWR/1 legacy rules: the signature covers a ' +
      'pipe-delimited rendering of credentialSubject ONLY, so id, type, issuer and hubInfo are UNSIGNED ' +
      'and are not attested by anyone (§12, §13.1)');

    var subject = doc.credentialSubject;
    var proof = Array.isArray(doc.proof) ? doc.proof[0] : doc.proof;
    var issuer = doc.issuer;
    var structural = true;
    if (!isPlainObject(subject)) { findings.error('AWR-DOC-008', 'credentialSubject is missing or not an object'); structural = false; }
    if (!isPlainObject(proof)) { findings.error('AWR-PROOF-001', 'proof is missing'); structural = false; }
    if (!isPlainObject(issuer)) { findings.error('AWR-DOC-010', 'issuer is missing or not an object'); structural = false; }
    checks.push({ check: 'structure', passed: structural });
    if (!structural) {
      return Promise.resolve(finishResult(doc, findings, {
        // §11.1: `awrVersion` and `documentType` report what the DOCUMENT carries.
        // An AWR/1 document has no `awrVersion` at all, so the answer is null and
        // AWR-LEGACY-001 is what names the dialect; inventing '1' and the type name
        // 'AIProvenanceReceipt' — which appears nowhere in the document — reported
        // two values no other implementation could agree with.
        awrVersion: typeof doc.awrVersion === 'string' ? doc.awrVersion : null,
        documentType: documentTypeOf(doc), profile: null,
        chain: { resolved: 0, unresolved: 0 }, checks: checks,
        legacy: {
          dialect: null, keySource: null, issuerAttested: false, verifiedKey: null,
          unsignedFields: ['id', 'type', 'issuer', 'hubInfo']
        },
        issuer: null
      }));
    }

    // §12.4 step 3: the caller's out-of-band key wins outright. Nothing the
    // document carries is substituted for it, and nothing is tried as a fallback
    // when it fails — a fallback hands the choice of key back to the sender.
    var keySource = null;
    var publicKey = null;
    if (o.expectedKey) {
      publicKey = o.expectedKey;
      keySource = 'caller';
    } else {
      // §12.2: publicKeyJwk, then publicKeyBase64, then issuer.id when it happens
      // to be a genuine did:key. AWR/1's own identifier was `did:key:` + the first
      // 32 characters of a base64 public key (Appendix D) and names no key at all.
      publicKey = legacyPublicKey(issuer);
      keySource = 'document';
      if (publicKey) {
        findings.warn('AWR-LEGACY-004', 'the AWR/1 signature was checked against key material ' +
          'carried by the document itself, which the AWR/1 signature does not cover; this shows ' +
          'only that the file is internally consistent and attests NO issuer identity (§12.4) — ' +
          'supply the expected key out of band to learn who signed');
      }
    }
    if (!publicKey) {
      findings.error('AWR-KEY-001', 'no AWR/1 signing key could be recovered: issuer.publicKeyJwk, ' +
        'issuer.publicKeyBase64 or a genuine did:key issuer.id is required (§12.2), or an expected ' +
        'key supplied out of band (§12.4). The AWR/1 identifier form was did:key: plus 32 base64 ' +
        'characters of the key, which names no key.');
    }
    checks.push({ check: 'key', passed: !!publicKey });

    // §12.4 step 4: two disagreeing statements about the signer are an error.
    var namedKey = issuerIdKey(issuer);
    if (publicKey && namedKey && !sameKey(namedKey, publicKey)) {
      findings.error('AWR-KEY-003', 'issuer.id names ' + didFromPublicKey(namedKey) +
        ' but the AWR/1 signature was to be checked against ' + didFromPublicKey(publicKey) +
        '; AWR/1 signs neither, so there is no way to tell which the issuer meant (§12.4)');
      publicKey = null;
      keySource = keySource;
    }

    var signature = null;
    if (typeof proof.proofValue !== 'string' || proof.proofValue.length === 0) {
      findings.error('AWR-PROOF-005', 'proofValue is missing');
    } else {
      try {
        signature = base64Decode(proof.proofValue);       // AWR/1 used base64
        if (signature.length !== 64) {
          findings.error('AWR-PROOF-005', 'legacy base64 proofValue decodes to ' + signature.length +
            ' bytes, not 64');
          signature = null;
        }
      } catch (e) {
        findings.error('AWR-PROOF-005', 'legacy proofValue is not valid base64');
      }
    }

    var dialects = ['A', 'B'];
    var canonicals = {};
    var renderable = true;
    try {
      dialects.forEach(function (d) { canonicals[d] = legacyPipeCanonical(subject, d); });
    } catch (e) {
      // §12.1: the value is outside the range in which the legacy form is
      // defined, so there is nothing to check the signature against.
      findings.error('AWR-LEGACY-002', e.detail || e.message);
      renderable = false;
    }

    var chainP;
    if (!publicKey || !signature || !renderable) {
      chainP = Promise.resolve(null);
    } else {
      chainP = dialects.reduce(function (p, d) {
        return p.then(function (hit) {
          if (hit) return hit;
          return verifyEd25519(publicKey, signature, utf8Encode(canonicals[d]), o)
            .then(function (ok) { return ok ? d : null; });
        });
      }, Promise.resolve(null));
    }

    return chainP.then(function (dialect) {
      checks.push({ check: 'signature', passed: !!dialect, algorithm: 'Ed25519 (AWR/1)' });
      if (publicKey && signature && renderable && !dialect) {
        findings.error('AWR-LEGACY-002', 'the signature verified under neither legacy dialect ' +
          '(A integer-preserving, B float-coercing)');
      }

      // §12: the AWR/2 subject rules (§3.3–3.5) postdate AWR/1 and MUST NOT be
      // applied to a legacy document — an AWR/1 receipt carried whatever its
      // issuer put there, and this section defines no subject shape at all. An
      // earlier revision of this file demanded 64-hex `inputHash`/`outputHash`
      // members and reported AWR-RCPT-001 when they were absent, which rejected
      // every AWR/1 receipt written by anyone else. What is reported for a legacy
      // document is AWR-LEGACY-001, the signature outcome, and nothing derived
      // from AWR/2's subject rules.
      var ts = subject.timestamp !== undefined ? Date.parse(subject.timestamp) : NaN;
      if (!isNaN(ts)) {
        if (ts > o.now + o.clockSkewSeconds * 1000) {
          findings.warn('AWR-TIME-001', 'timestamp (' + subject.timestamp + ') is in the future beyond the ' +
            o.clockSkewSeconds + 's skew allowance');
        }
        if (o.maxAgeDays != null && (o.now - ts) / 86400000 > o.maxAgeDays) {
          findings.warn('AWR-TIME-002', 'document is ' + Math.floor((o.now - ts) / 86400000) +
            ' days old, beyond the caller\'s ' + o.maxAgeDays + '-day policy window; age is not a ' +
            'validity property (§11.3)');
        }
      }

      if (subject.teeAttestation !== undefined) {
        findings.warn('AWR-ENV-001', 'teeAttestation is present and was NOT verified. The previous ' +
          'revision of this page checked its inner signature with the RECEIPT ISSUER\'S key, which proves ' +
          'only that the party making the claim also wrote it down while presenting as hardware evidence ' +
          '(§7.3)');
      }

      // AWR/1 `parentReceipts` were identifier strings with no digest, so the
      // edges are not content-addressed and can be re-pointed (§13.1). That is
      // worth telling the reader, but AWR-CHAIN-001 means "a parents entry has no
      // digestSRI" and carries severity `error`; emitting it at warning severity
      // would put an error code in `warnings` (§11.1). It goes in `legacy.notes`.
      var parents = Array.isArray(subject.parentReceipts) ? subject.parentReceipts : [];
      var notes = [];
      if (parents.length > 0) {
        notes.push(parents.length + ' AWR/1 parent reference(s) are identifier strings with no ' +
          'digest, so the edges are not content-addressed and can be re-pointed (§13.1)');
      }

      return finishResult(doc, findings, {
        // §11.1, as above: the document's own values, null when it carries none.
        awrVersion: typeof doc.awrVersion === 'string' ? doc.awrVersion : null,
        documentType: documentTypeOf(doc), profile: null,
        // §11.1: `chain` counts §8.1 `parents` edges. AWR/1 `parentReceipts` are
        // identifier strings with no digest, so they are not §8.1 edges and are not
        // counted; `legacy.notes` below is where the reader is told they exist and
        // why they are re-pointable.
        chain: { resolved: 0, unresolved: 0 }, checks: checks,
        // §12.4: an AWR/1 result names a KEY, never an issuer. `issuerAttested`
        // is a constant, and present *because* it is a constant: AWR/1 can never
        // attest an issuer, and a member that is always false is read while an
        // absent one is not.
        legacy: {
          dialect: dialect,
          keySource: keySource,
          issuerAttested: false,
          verifiedKey: dialect ? didFromPublicKey(publicKey) : null,
          canonical: dialect ? canonicals[dialect] : null,
          unsignedFields: ['id', 'type', 'issuer', 'hubInfo'],
          notes: notes
        },
        // §12.4: `issuer` is written by whoever handed you the file and is
        // outside the AWR/1 signature. Echoing it beside `valid: true` is the
        // whole exploit — the caller reads a boolean and a DID and concludes the
        // DID's owner signed something. The unsigned copy stays reachable under
        // `legacy.unsignedIssuer`, clearly labelled.
        issuer: null,
        legacyUnsignedIssuer: isPlainObject(issuer) ? issuer : null
      });
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 13. Entry points
  // ─────────────────────────────────────────────────────────────────────────

  function withDefaults(opts) {
    var o = {};
    Object.keys(DEFAULTS).forEach(function (k) { o[k] = DEFAULTS[k]; });
    if (opts) Object.keys(opts).forEach(function (k) { if (opts[k] !== undefined) o[k] = opts[k]; });
    if (o.now === undefined || o.now === null) o.now = Date.now();
    else if (typeof o.now === 'string') o.now = Date.parse(o.now);
    else if (o.now instanceof Date) o.now = o.now.getTime();
    return o;
  }

  // §11.1: `verifiedProof` is non-null IF AND ONLY IF the result reports no
  // AWR-CANON-*, no AWR-KEY-* and no AWR-PROOF-* code. Those three families are
  // exactly the conditions §6.3 lists as making step 6 impossible, plus step 6's
  // own failure: no canonical form, no authoritative public key (AWR-KEY-003
  // included — §5.2 leaves none when publicKeyJwk contradicts the did:key), or a
  // proof configuration AWR/2 does not define. Every other code — semantic, chain,
  // profile — leaves the signature check untouched, so the index survives an
  // invalid document. Deriving it here rather than trusting the call site is what
  // stopped this page reporting `verifiedProof: 0` beside AWR-KEY-003.
  var NO_SIGNATURE_CHECK = /^AWR-(CANON|KEY|PROOF)-/;

  function verifiedProofOf(findings, index) {
    for (var i = 0; i < findings.reasons.length; i++) {
      if (NO_SIGNATURE_CHECK.test(findings.reasons[i].code)) return null;
    }
    return index;
  }

  // §11.1: `awrVersion` and `documentType` are null whenever any AWR-CANON-* code is
  // reported. A document with no canonical form (§4) has no confirmed content — §4.3
  // exists because the bytes it canonicalizes to are not the bytes its issuer signed —
  // and leaving the two free made them a property of the parser's architecture rather
  // than of the document: this page reads `type` off the lone-surrogate document, which
  // the Rust build's parser rejects before it sees `type`, and cannot read it off the
  // `2340.0` document, which the Rust build does reach.
  function noCanonicalForm(findings) {
    for (var i = 0; i < findings.reasons.length; i++) {
      if (findings.reasons[i].code.indexOf('AWR-CANON-') === 0) return true;
    }
    return false;
  }

  function finishResult(doc, findings, extra) {
    var suppress = noCanonicalForm(findings);
    var result = {
      valid: findings.valid(),
      awrVersion: suppress ? null : extra.awrVersion,
      documentType: suppress ? null : extra.documentType,
      profile: extra.profile !== undefined ? extra.profile : null,
      reasons: findings.reasons,
      warnings: findings.warnings,
      chain: extra.chain || { resolved: 0, unresolved: 0 },
      // §11.1: REQUIRED whenever §6.3 step 6 was performed and succeeded, whether
      // `proof` was one object or an array; null when no proof verified. Present on
      // every result so that a caller can read it without knowing which
      // implementation produced the result, and derived from the codes reported
      // rather than trusted from the call site — see verifiedProofOf.
      verifiedProof: verifiedProofOf(findings,
        extra.verifiedProof === undefined ? null : extra.verifiedProof)
    };
    // Non-normative extras the page renders. §11.1 permits additional members and
    // requires a consumer to ignore the ones it does not know.
    result.checks = extra.checks || [];
    result.legacy = extra.legacy || null;
    // §12.4: the legacy path passes `issuer: null` explicitly, because an AWR/1
    // `issuer` is unsigned and MUST NOT be reported as an attested identity.
    result.issuer = Object.prototype.hasOwnProperty.call(extra, 'issuer')
      ? extra.issuer
      : (isPlainObject(doc) && isPlainObject(doc.issuer) ? doc.issuer : null);
    if (extra.legacyUnsignedIssuer !== undefined) {
      result.legacyUnsignedIssuer = extra.legacyUnsignedIssuer;
    }
    if (extra.references) result.references = extra.references;
    result.proofDetail = extra.proofDetail || null;
    result.profiles = extra.profiles || null;
    if (extra.proofs) result.proofs = extra.proofs;
    // Kept for backwards compatibility with the previous result shape: a flat
    // list of human-readable error strings.
    result.errors = findings.reasons.map(function (r) { return r.code + ': ' + r.detail; });
    return result;
  }

  /**
   * Verify one AWR/2 document (§6.3), optionally against caller-supplied
   * related documents for §8 chain resolution and §10 profiles.
   *
   * opts: { profile, parents: [doc], now, maxAgeDays, chainMaxDepth,
   *         chainMaxNodes, clockSkewSeconds, forceEd25519Backend }
   */
  function verifyAwr2(doc, opts) {
    var o = withDefaults(opts);
    var findings = new Findings();
    var checks = [];

    if (!isPlainObject(doc)) {
      findings.error('AWR-DOC-001', 'input is not a JSON object');
      return Promise.resolve(finishResult(doc, findings, {
        awrVersion: null, documentType: null, checks: [{ check: 'structure', passed: false }]
      }));
    }

    // §4.3 / §4.1(3,4): every number, string and property name must be
    // canonicalizable before anything else can be trusted. All offending values
    // are reported, not just the first (§11.1).
    var canonicalOk = true;
    var canonicalErrors = collectCanonicalizationErrors(doc, o);
    canonicalErrors.forEach(function (e) { findings.error(e.code, e.detail); canonicalOk = false; });
    checks.push({ check: 'canonical', passed: canonicalOk });

    if (canonicalOk) {
      try {
        var canon = jcsCanonicalize(doc, o);
        if (!jcsSelfCheck(canon, o)) {
          findings.error('AWR-CANON-006', 'canonicalizer self-check failed: re-canonicalizing the canonical ' +
            'form did not reproduce it');
          canonicalOk = false;
        }
      } catch (e) {
        findings.error(e.code || 'AWR-CANON-005', e.detail || e.message);
        canonicalOk = false;
      }
    }

    var documentType = checkEnvelope(doc, findings);
    checkTimeWarnings(doc, findings, o);
    checks.push({ check: 'structure', passed: !findings.hasCode('AWR-DOC-001') && documentType !== null });

    // §5: issuer key.
    var key = null;
    if (isPlainObject(doc.issuer) && typeof doc.issuer.id === 'string') {
      try {
        key = parseDidKey(doc.issuer.id);
        checkPublicKeyJwk(doc.issuer.publicKeyJwk, key.publicKey, findings);
      } catch (e) {
        findings.error(e.code || 'AWR-KEY-002', e.detail || e.message);
      }
    }
    checks.push({ check: 'key', passed: !!key && !findings.hasCode('AWR-KEY-003') && !findings.hasCode('AWR-KEY-004') });

    // §3.3–3.5 subject semantics.
    var subject = isPlainObject(doc.credentialSubject) ? doc.credentialSubject : null;
    var semanticErrorsBefore = findings.reasons.length;
    if (subject) {
      if (documentType === 'WorkReceipt') checkWorkReceipt(subject, findings, o);
      else if (documentType === 'VerificationVerdict') checkVerdict(subject, findings, o);
      else if (documentType === 'BlameAttestation') checkBlame(subject, findings, o);
    }
    checks.push({ check: 'semantics', passed: findings.reasons.length === semanticErrorsBefore });

    // §6 proof.
    var proofs = doc.proof === undefined ? [] : (Array.isArray(doc.proof) ? doc.proof : [doc.proof]);
    var proofResults = [];
    var proofNotes = [];
    if (proofs.length === 0) {
      findings.error('AWR-PROOF-001', 'proof is missing');
      checks.push({ check: 'signature', passed: false });
      return finalize(null);
    }

    var chainP = proofs.reduce(function (p, proof, index) {
      return p.then(function () {
        if (!isPlainObject(proof)) {
          findings.error('AWR-PROOF-002', 'proof[' + index + '] is not an object');
          proofResults.push({ index: index, verified: false, checked: false });
          return null;
        }
        var localFindings = proofs.length === 1 ? findings : new Findings();
        var configOk = checkProofConfig(proof, doc, key && key.did, key && key.multibase, localFindings);
        var signature = decodeProofValue(proof.proofValue, localFindings);
        if (proofs.length > 1) {
          // §6.1: a sibling proof's problems must not by themselves invalidate the
          // document, and must NOT be re-emitted as warnings under their own
          // error-severity codes — a code has one severity (§11.1). They are
          // carried in the non-normative `proofs` member instead.
          proofNotes.push({
            index: index,
            problems: localFindings.reasons.concat(localFindings.warnings).map(function (r) {
              return r.code + ': ' + r.detail;
            })
          });
        }
        if (!configOk || !signature || !key || !canonicalOk) {
          proofResults.push({ index: index, verified: false, checked: false });
          return null;
        }
        return computeHashData(doc, proof, o).then(function (h) {
          return verifyEd25519(key.publicKey, signature, h.hashData, o).then(function (ok) {
            proofResults.push({
              index: index, verified: ok, checked: true,
              proofConfigHash: toHex(h.proofConfigHash),
              transformedDocumentHash: toHex(h.transformedDocumentHash),
              hashData: toHex(h.hashData)
            });
            return null;
          });
        }).catch(function (e) {
          findings.error(e.code || 'AWR-PROOF-006', e.detail || e.message);
          proofResults.push({ index: index, verified: false, checked: !e.code });
          return null;
        });
      });
    }, Promise.resolve());

    return chainP.then(function () {
      var verified = null, anyChecked = false;
      for (var i = 0; i < proofResults.length; i++) {
        if (proofResults[i].checked) anyChecked = true;
        if (proofResults[i].verified && verified === null) verified = proofResults[i];
      }
      if (!verified) {
        // §6.3: AWR-PROOF-006 means the signature WAS checked and did not verify.
        // When an earlier step made the check impossible — no canonical form, no
        // derivable key, a proof configuration that is not the one AWR/2 defines —
        // that step's code is the report and PROOF-006 must not be added. The
        // document is invalid either way: every such condition is an error.
        if (anyChecked) {
          findings.error('AWR-PROOF-006', proofs.length > 1
            ? 'no proof in the array verified against the issuer key'
            : 'Ed25519 signature verification failed over hashData = ' +
              'SHA-256(JCS(proofConfig)) || SHA-256(JCS(document−proof))');
        } else if (findings.reasons.length === 0) {
          // Fail closed: the check did not run and nothing said why, which is a
          // bug in this file rather than a property of the document (§6.3).
          findings.error('AWR-PROOF-006', 'the signature was not checked and no reason was ' +
            'recorded; refusing to report a document as valid on that basis');
        }
      }
      checks.push({ check: 'signature', passed: !!verified, algorithm: 'Ed25519 / ' + CRYPTOSUITE });
      return finalize(verified);
    });

    function finalize(verifiedProof) {
      // §8 + §10 need this document's own secured digest and those of any
      // caller-supplied related documents.
      var related = [];
      if (Array.isArray(o.parents)) related = related.concat(o.parents);
      if (Array.isArray(o.related)) related = related.concat(o.related);
      var docs = [doc].concat(related.filter(function (d) { return isPlainObject(d) && d !== doc; }));

      return buildPool(docs, o, findings).then(function (pool) {
        var chain = { resolved: 0, unresolved: 0 };
        var references = null;
        var chainOk = true;
        if (documentType === 'WorkReceipt' && canonicalOk) {
          var before = findings.reasons.length;
          chain = resolveChain(doc, pool, findings, o);
          chainOk = findings.reasons.length === before;
        } else if (documentType === 'VerificationVerdict' && subject &&
                   isPlainObject(subject.verifiedWork) && canonicalOk) {
          // §3.4 / VDCT-005: only meaningful when a receipt was supplied.
          //
          // §11.1: `chain` counts §8.1 `parents` edges and nothing else. A
          // verdict's `verifiedWork` is a digest reference (§3.2) but is not a
          // chain edge, and reporting it here said `unresolved: 1` for a
          // standalone verdict — telling a caller a hop went unchecked on a
          // document that names no hop, which is the opposite of the "chain
          // intact" / "chain not checked" distinction the member exists for.
          // The outcome of this check is AWR-VDCT-005; the counts stay at zero
          // and the resolution goes in the non-normative `references` member.
          var receipts = pool.filter(function (e) { return e.type === 'WorkReceipt'; });
          if (receipts.length > 0) {
            var match = receipts.filter(function (e) { return e.sri === subject.verifiedWork.digestSRI; });
            if (match.length === 0) {
              findings.error('AWR-VDCT-005', 'verifiedWork.digestSRI does not match any supplied WorkReceipt');
              chainOk = false;
            } else {
              references = { verifiedWork: 'resolved' };
            }
          } else {
            references = { verifiedWork: 'not-supplied' };
          }
        } else if (documentType === 'BlameAttestation' && subject && canonicalOk) {
          // Same rule: a BlameAttestation's `chain` and `blamedWork` are digest
          // references, not §8.1 edges. The reachability walk's outcome is
          // AWR-BLAME-001; its counts are reported outside `chain` (§11.1).
          var b = checkBlameReachability(subject, pool, findings);
          references = { blameWalk: b.chain };
          chainOk = b.ok;
        }
        checks.push({ check: 'chain', passed: chainOk });

        return markPoolValidity(pool, doc, verifiedProof, o).then(function () {
          var profile = null, profiles = null;
          if (documentType === 'WorkReceipt') {
            var self = null;
            for (var i = 0; i < pool.length; i++) if (pool[i].doc === doc) self = pool[i];
            if (self) {
              var pr = evaluateProfiles(self, pool, findings, o);
              profile = verifiedProof && findings.valid() ? pr.profile : null;
              profiles = pr.evaluated;
            }
          }
          checks.push({ check: 'profile', passed: profile !== null, value: profile || undefined });

          return finishResult(doc, findings, {
            awrVersion: typeof doc.awrVersion === 'string' ? doc.awrVersion : null,
            documentType: documentType,
            profile: profile,
            chain: chain,
            references: references,
            checks: checks,
            profiles: profiles,
            proofDetail: verifiedProof,
            // §6.1 / §11.1: which proof verified. REQUIRED when the document
            // carried an array of proofs and one of them verified.
            verifiedProof: verifiedProof ? verifiedProof.index : null,
            proofs: proofNotes.length ? proofNotes : null
          });
        });
      });
    }
  }

  /**
   * §10.2 says "at least one **valid** VerificationVerdict", so a verdict only
   * contributes to a profile once its own proof has been checked. The subject's
   * validity is already known; a caller that verified the other documents
   * itself (as verifyBundle does) passes them in `validatedDocs`; anything left
   * over is verified here with `_inner` set, which switches off profile
   * evaluation and related-document loading so the recursion is exactly one
   * level deep and cannot loop.
   */
  function markPoolValidity(pool, subjectDoc, verifiedProof, o) {
    return pool.reduce(function (p, entry) {
      return p.then(function () {
        if (entry.doc === subjectDoc) { entry.valid = !!verifiedProof; return null; }
        if (Array.isArray(o.validatedDocs) && o.validatedDocs.indexOf(entry.doc) >= 0) {
          entry.valid = true;
          return null;
        }
        if (o._inner || entry.type !== 'VerificationVerdict') return null;
        var inner = Object.assign({}, o, { _inner: true, profile: null, related: [], parents: [] });
        return verifyAwr2(entry.doc, inner).then(function (r) { entry.valid = r.valid; return null; });
      });
    }, Promise.resolve());
  }

  function checkBlameReachability(subject, pool, findings) {
    var byDigest = Object.create(null);
    pool.forEach(function (e) { byDigest[e.sri] = e; });
    var chainRef = isPlainObject(subject.chain) ? subject.chain.digestSRI : null;
    var blamed = isPlainObject(subject.blamedWork) ? subject.blamedWork.digestSRI : null;
    if (!chainRef || !blamed) return { ok: true, chain: { resolved: 0, unresolved: 2 } };
    if (chainRef === blamed) return { ok: true, chain: { resolved: byDigest[chainRef] ? 1 : 0, unresolved: byDigest[chainRef] ? 0 : 1 } };
    var start = byDigest[chainRef];
    if (!start) return { ok: true, chain: { resolved: 0, unresolved: 2 } };   // not checkable, not an error
    var seen = Object.create(null), stack = [chainRef], resolved = 0, found = false;
    while (stack.length) {
      var cur = stack.pop();
      if (seen[cur]) continue;
      seen[cur] = true;
      var entry = byDigest[cur];
      if (!entry) continue;
      resolved++;
      if (cur === blamed) { found = true; break; }
      var parents = (isPlainObject(entry.doc.credentialSubject) && entry.doc.credentialSubject.parents) || [];
      if (Array.isArray(parents)) {
        parents.forEach(function (r) { if (isPlainObject(r) && typeof r.digestSRI === 'string') stack.push(r.digestSRI); });
      }
    }
    if (!found && byDigest[blamed]) {
      findings.error('AWR-BLAME-001', 'blamedWork is not reachable from chain through the supplied receipts');
      return { ok: false, chain: { resolved: resolved, unresolved: 0 } };
    }
    return { ok: true, chain: { resolved: resolved, unresolved: byDigest[blamed] ? 0 : 1 } };
  }

  function documentTypeOf(doc) {
    if (!isPlainObject(doc) || !Array.isArray(doc.type)) return null;
    for (var i = 0; i < AWR_TYPES.length; i++) if (doc.type.indexOf(AWR_TYPES[i]) >= 0) return AWR_TYPES[i];
    return null;
  }

  /** Digest every document once; §8/§10 work over digests, never identifiers. */
  function buildPool(docs, o, findings) {
    return docs.reduce(function (p, d) {
      return p.then(function (acc) {
        var entry = { doc: d, type: documentTypeOf(d), sri: null, valid: false };
        return sriOfDocument(d, o).then(function (sri) {
          entry.sri = sri;
          acc.push(entry);
          return acc;
        }).catch(function () {
          // A related document that cannot be canonicalized simply cannot
          // participate in chain resolution; its own verification would report
          // the canonicalization error.
          return acc;
        });
      });
    }, Promise.resolve([])).then(function (pool) {
      var byId = Object.create(null);
      pool.forEach(function (e) {
        var id = isPlainObject(e.doc) ? e.doc.id : null;
        if (typeof id !== 'string') return;
        if (byId[id] && byId[id] !== e.sri) {
          findings.error('AWR-BUNDLE-002', 'two supplied documents share id ' + id + ' with differing content');
        }
        byId[id] = e.sri;
      });
      return pool;
    });
  }

  /** Walks a parsed value collecting every §4.3 / §4.1(4) violation. */
  function collectCanonicalizationErrors(value, o) {
    var out = [];
    var seenPaths = Object.create(null);
    function add(code, detail) {
      var k = code + detail;
      if (seenPaths[k]) return;
      seenPaths[k] = true;
      out.push({ code: code, detail: detail });
    }
    function walk(v, where, depth) {
      if (depth > o.maxJsonDepth) {
        add('AWR-CANON-005', 'value nesting deeper than the configured limit of ' + o.maxJsonDepth);
        return;
      }
      if (v === null) return;
      var t = typeof v;
      if (t === 'number' || t === 'string') {
        try { jcsSerialize(v, where, depth, o.maxJsonDepth); } catch (e) { add(e.code, e.detail); }
        return;
      }
      if (t === 'boolean') return;
      if (Array.isArray(v)) {
        for (var i = 0; i < v.length; i++) walk(v[i], where + '[' + i + ']', depth + 1);
        return;
      }
      if (t === 'object') {
        var keys = Object.keys(v);
        for (var k = 0; k < keys.length; k++) {
          try { jcsString(keys[k], where + '/' + keys[k] + ' (property name)'); } catch (e) { add(e.code, e.detail); }
          walk(v[keys[k]], where + '/' + keys[k], depth + 1);
        }
        return;
      }
      add('AWR-CANON-005', 'value of type ' + t + ' at ' + where + ' is not JSON data');
    }
    walk(value, '$', 0);
    return out;
  }

  /**
   * Verify a document, a bundle (§9), or a JSON string. Dispatches AWR/2 vs the
   * AWR/1 legacy path (§12).
   */
  function verify(input, opts) {
    var o = withDefaults(opts);
    var doc = input;
    if (typeof input === 'string') {
      try {
        doc = parseAwrJson(input, o);
      } catch (e) {
        // §4.3 is a rule about documents signed under AWR/2. An AWR/1 document
        // predates it, so when the strict parse failed *only* on a number, the
        // bytes are re-read leniently and, if what comes out is AWR/1,
        // verification continues on the legacy path (§12).
        var lenient = null;
        if (e.code === 'AWR-CANON-001' || e.code === 'AWR-CANON-002') {
          try {
            var relaxed = Object.assign({}, o, { allowNonIntegerNumbers: true });
            var candidate = parseAwrJson(input, relaxed);
            if (looksLegacy(candidate)) lenient = candidate;
          } catch (ignored) { lenient = null; }
        }
        if (lenient === null) {
          var f = new Findings();
          f.error(e.code || 'AWR-CANON-005', e.detail || e.message);
          return Promise.resolve(finishResult(null, f, {
            awrVersion: null, documentType: null, checks: [{ check: 'canonical', passed: false }]
          }));
        }
        doc = lenient;
      }
    }
    if (isPlainObject(doc) && doc.awrBundle !== undefined) return verifyBundle(doc, o);
    // §12.3: the version gate runs before any verification. Selecting the rule
    // set on `proof.type` alone was an unauthenticated forgery path — AWR/1 signs
    // neither `proof.type` nor `issuer`.
    var klass = classifyVersion(doc);
    if (klass === 'disagree') {
      var df = new Findings();
      df.error('AWR-LEGACY-003', 'version signals disagree: the document carries an AWR/1 ' +
        'Ed25519Signature2018 proof and the AWR/2 signal(s) ' + awr2Signals(doc).join(', ') +
        '. AWR/1 does not sign proof.type or issuer, so honouring the proof suite here would let ' +
        'the sender choose which rules apply to a document that claims to be AWR/2 (§12.3); it is ' +
        'verified under neither, and there is no fallback to the other rule set');
      return Promise.resolve(finishResult(doc, df, {
        awrVersion: typeof doc.awrVersion === 'string' ? doc.awrVersion : null,
        documentType: documentTypeOf(doc), profile: null,
        chain: { resolved: 0, unresolved: 0 },
        checks: [{ check: 'version', passed: false }],
        issuer: null
      }));
    }
    if (klass === 'awr1') {
      if (o.noLegacy) {
        var nf = new Findings();
        nf.error('AWR-LEGACY-005', 'the document is an AWR/1 legacy document (§12) and this ' +
          'verifier was asked not to apply the AWR/1 rules; §12 support is OPTIONAL');
        return Promise.resolve(finishResult(doc, nf, {
          awrVersion: null, documentType: documentTypeOf(doc), profile: null,
          chain: { resolved: 0, unresolved: 0 },
          checks: [{ check: 'version', passed: false }],
          issuer: null
        }));
      }
      return verifyLegacy(doc, o);
    }
    return verifyAwr2(doc, o);
  }

  /** §9: a bundle is a transport container; every claim inside is verified individually. */
  function verifyBundle(bundle, opts) {
    var o = withDefaults(opts);
    var findings = new Findings();
    if (bundle.awrBundle !== '2.0' || !Array.isArray(bundle.documents) || bundle.documents.length === 0) {
      findings.error('AWR-BUNDLE-001', 'awrBundle must be "2.0" and documents must be a non-empty array');
      return Promise.resolve(finishResult(null, findings, {
        awrVersion: null, documentType: null, checks: [{ check: 'structure', passed: false }]
      }));
    }
    var docs = bundle.documents;
    // §9: the subject is the caller's explicit argument, or the single
    // WorkReceipt that nobody references as a parent. Ambiguity is reported,
    // never guessed.
    var receipts = docs.filter(function (d) { return documentTypeOf(d) === 'WorkReceipt'; });
    var subjectDoc = null;
    if (o.subjectId) {
      subjectDoc = docs.filter(function (d) { return isPlainObject(d) && d.id === o.subjectId; })[0] || null;
      if (!subjectDoc) findings.error('AWR-BUNDLE-003', 'no document in the bundle has id ' + o.subjectId);
    }
    return buildPool(docs, o, findings).then(function (pool) {
      // §9: subject selection runs ONLY when a profile is requested. Without one a bundle
      // is a transport container and nothing more — verify every document in it and report
      // the conjunction. A bundle holding a single VerificationVerdict is therefore valid
      // here and AWR-BUNDLE-003 at any profile; three implementations answered that exact
      // bundle three different ways before §9 said when selection applies.
      if (!o.profile && !o.subjectId) {
        return docs.reduce(function (p, d, index) {
          return p.then(function (acc) {
            return verify(d, Object.assign({}, o, { profile: null, related: docs, _inner: true }))
              .then(function (r) { acc.push({ index: index, result: r }); return acc; });
          });
        }, Promise.resolve([])).then(function (all) {
          all.forEach(function (e) {
            // Not prefixed with the document index: findings dedup on (code, detail), and
            // two documents failing the same way for the same stated reason are one fact
            // about the bundle. Prefixing made AWR-CHAIN-005 appear twice for a bundle
            // whose every document breached the same limit.
            (e.result.reasons || []).forEach(function (x) { findings.error(x.code, x.detail); });
            (e.result.warnings || []).forEach(function (x) { findings.warn(x.code, x.detail); });
          });
          // §11.1: verifiedProof must name the proof that was checked. A container has no
          // subject, so it reports documents[0]'s value — deterministic, and the only
          // reading that stays true for the single-document bundle.
          var firstProof = all.length && all[0].result ? all[0].result.verifiedProof : null;
          return finishResult(null, findings, {
            awrVersion: null, documentType: null,
            verifiedProof: firstProof,
            chain: { resolved: 0, unresolved: 0 }
          });
        });
      }

      if (!subjectDoc) {
        var referenced = Object.create(null);
        pool.forEach(function (e) {
          var parents = (isPlainObject(e.doc.credentialSubject) && e.doc.credentialSubject.parents) || [];
          if (Array.isArray(parents)) {
            parents.forEach(function (r) { if (isPlainObject(r) && r.digestSRI) referenced[r.digestSRI] = true; });
          }
        });
        var roots = pool.filter(function (e) { return e.type === 'WorkReceipt' && !referenced[e.sri]; });
        if (roots.length === 1) {
          subjectDoc = roots[0].doc;
        } else {
          // §9: ambiguity MUST be reported rather than resolved by guessing, so
          // there is deliberately no "well, there is only one receipt" fallback.
          findings.error('AWR-BUNDLE-003', 'the subject document is ambiguous: ' + roots.length +
            ' WorkReceipt(s) unreferenced as anyone\'s parent, out of ' + receipts.length +
            ' receipt(s) in a bundle of ' + docs.length + ' document(s); pass subjectId to disambiguate');
        }
      }
      if (!subjectDoc) {
        return finishResult(null, findings, {
          awrVersion: null, documentType: null, checks: [{ check: 'structure', passed: false }],
          chain: { resolved: 0, unresolved: 0 }
        });
      }
      // Verify every non-subject document so profile evaluation only counts
      // verdicts that are themselves valid (§10.2 "at least one *valid*
      // VerificationVerdict").
      var others = docs.filter(function (d) { return d !== subjectDoc; });
      return others.reduce(function (p, d) {
        return p.then(function (acc) {
          return verify(d, Object.assign({}, o, { profile: null, related: docs, _inner: true }))
            .then(function (r) { acc.push({ doc: d, result: r }); return acc; });
        });
      }, Promise.resolve([])).then(function (sub) {
        var validDocs = sub.filter(function (s) { return s.result.valid; }).map(function (s) { return s.doc; });
        // A bundled document that is itself invalid does not contribute to any
        // profile (§10.2). That fact is worth showing, but AWR-BUNDLE-002 means
        // "duplicate id with differing content" and carries severity `error`, so
        // re-using it here at warning severity would make the result
        // uncomparable (§11.1). It goes in a non-normative member instead.
        var invalidMembers = sub.filter(function (s) { return !s.result.valid; }).map(function (s) {
          return {
            id: s.doc && s.doc.id,
            reasons: s.result.reasons.map(function (r) { return r.code; })
          };
        });
        // All documents take part in chain resolution (a broken parent still
        // pins its own bytes), but only the ones that verified may contribute to
        // a profile (§10.2).
        return verify(subjectDoc, Object.assign({}, o, { related: docs, validatedDocs: validDocs }))
          .then(function (result) {
          // Merge bundle-level findings into the subject's result.
          findings.reasons.forEach(function (r) { result.reasons.push(r); });
          findings.warnings.forEach(function (r) { result.warnings.push(r); });
          result.valid = result.reasons.length === 0;
          result.errors = result.reasons.map(function (r) { return r.code + ': ' + r.detail; });
          result.bundle = {
            documents: docs.length,
            verified: sub.length + 1,
            invalidMembers: invalidMembers
          };
          return result;
        });
      });
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 14. Self-contained Ed25519 verification (RFC 8032), used when the host has
  //     no Ed25519 in WebCrypto. BigInt field arithmetic; SHA-512 comes from
  //     crypto.subtle so no hash implementation is duplicated here.
  // ─────────────────────────────────────────────────────────────────────────

  var ED_P = null, ED_D = null, ED_L = null, ED_I = null, ED_BASE = null;
  function edInit() {
    if (ED_P !== null) return;
    ED_P = (BigInt(2) ** BigInt(255)) - BigInt(19);
    ED_D = BigInt('37095705934669439343138083508754565189542113879843219016388785533085940283555');
    ED_L = (BigInt(2) ** BigInt(252)) + BigInt('27742317777372353535851937790883648493');
    ED_I = BigInt('19681161376707505956807079304988542015446066515923890162744021073123829784752');
    ED_BASE = {
      x: BigInt('15112221349535400772501151409588531511454012693041857206046113283949847762202'),
      y: BigInt('46316835694926478169428394003475163141307993866256225615783033603165251855960')
    };
  }
  function edMod(a) { var r = a % ED_P; return r < BigInt(0) ? r + ED_P : r; }
  function edPow(base, exp) {
    var result = BigInt(1), b = edMod(base), e = exp;
    while (e > BigInt(0)) {
      if (e & BigInt(1)) result = edMod(result * b);
      b = edMod(b * b);
      e >>= BigInt(1);
    }
    return result;
  }
  function edInv(a) { return edPow(a, ED_P - BigInt(2)); }

  // Extended coordinates (X:Y:Z:T); the unified add-2008-hwcd-3 formula is
  // valid for doubling too, so one routine covers both.
  function edAdd(p, q) {
    var A = edMod((p.y - p.x) * (q.y - q.x));
    var B = edMod((p.y + p.x) * (q.y + q.x));
    var C = edMod(p.t * BigInt(2) * ED_D * q.t);
    var D = edMod(p.z * BigInt(2) * q.z);
    var E = B - A, F = D - C, G = D + C, H = B + A;
    return { x: edMod(E * F), y: edMod(G * H), t: edMod(E * H), z: edMod(F * G) };
  }
  function edMul(point, scalar) {
    var q = { x: BigInt(0), y: BigInt(1), z: BigInt(1), t: BigInt(0) };
    var p = point, n = scalar;
    while (n > BigInt(0)) {
      if (n & BigInt(1)) q = edAdd(q, p);
      p = edAdd(p, p);
      n >>= BigInt(1);
    }
    return q;
  }
  function edFromAffine(a) { return { x: edMod(a.x), y: edMod(a.y), z: BigInt(1), t: edMod(a.x * a.y) }; }
  function edToBytes(p) {
    var zi = edInv(p.z);
    var x = edMod(p.x * zi), y = edMod(p.y * zi);
    var out = new Uint8Array(32);
    var v = y;
    for (var i = 0; i < 32; i++) { out[i] = Number(v & BigInt(255)); v >>= BigInt(8); }
    out[31] |= Number(x & BigInt(1)) << 7;
    return out;
  }
  function edLeToBigInt(bytes) {
    var v = BigInt(0);
    for (var i = bytes.length - 1; i >= 0; i--) v = (v << BigInt(8)) | BigInt(bytes[i]);
    return v;
  }
  function edDecodePoint(bytes) {
    var yBytes = new Uint8Array(bytes.subarray(0, 32));
    var sign = (yBytes[31] >> 7) & 1;
    yBytes[31] &= 0x7f;
    var y = edLeToBigInt(yBytes);
    if (y >= ED_P) return null;                                  // non-canonical
    var y2 = edMod(y * y);
    var u = edMod(y2 - BigInt(1));
    var v = edMod(edMod(ED_D * y2) + BigInt(1));
    var x2 = edMod(u * edInv(v));
    if (x2 === BigInt(0)) {
      if (sign) return null;
      return edFromAffine({ x: BigInt(0), y: y });
    }
    var x = edPow(x2, (ED_P + BigInt(3)) / BigInt(8));
    if (edMod(x * x) !== x2) x = edMod(x * ED_I);
    if (edMod(x * x) !== x2) return null;                        // not on curve
    if (Number(x & BigInt(1)) !== sign) x = edMod(ED_P - x);
    return edFromAffine({ x: x, y: y });
  }

  /** RFC 8032 §5.1.7 verification, cofactorless: [S]B == R + [k]A. */
  function ed25519VerifyBigInt(publicKey, signature, message) {
    if (typeof BigInt === 'undefined') return Promise.resolve(false);
    edInit();
    if (!publicKey || publicKey.length !== 32 || !signature || signature.length !== 64) {
      return Promise.resolve(false);
    }
    var A = edDecodePoint(publicKey);
    var R = edDecodePoint(signature.subarray(0, 32));
    if (!A || !R) return Promise.resolve(false);
    var S = edLeToBigInt(signature.subarray(32, 64));
    if (S >= ED_L) return Promise.resolve(false);                 // malleable
    var pre = new Uint8Array(64 + message.length);
    pre.set(signature.subarray(0, 32), 0);
    pre.set(publicKey, 32);
    pre.set(message, 64);
    return sha512(pre).then(function (h) {
      var k = edLeToBigInt(h) % ED_L;
      var sB = edMul(edFromAffine(ED_BASE), S);
      var kA = edMul(A, k);
      return bytesEqual(edToBytes(sB), edToBytes(edAdd(R, kA)));
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 15. Exports
  // ─────────────────────────────────────────────────────────────────────────

  var API = {
    // spec constants
    VC2_CONTEXT: VC2_CONTEXT,
    AWR2_CONTEXT: AWR2_CONTEXT,
    AWR_TYPES: AWR_TYPES,
    DEFAULTS: DEFAULTS,
    // §4
    parseAwrJson: parseAwrJson,
    jcsCanonicalize: jcsCanonicalize,
    jcsCanonicalizeBytes: jcsCanonicalizeBytes,
    jcsSelfCheck: jcsSelfCheck,
    decimalCompare: decimalCompare,
    // §3.2
    sriFromBytes: sriFromBytes,
    sriOfDocument: sriOfDocument,
    checkSri: checkSri,
    // §5
    parseDidKey: parseDidKey,
    base58btcDecode: base58btcDecode,
    base58btcEncode: base58btcEncode,
    base64Decode: base64Decode,
    base64Encode: base64Encode,
    // §6
    computeHashData: computeHashData,
    verifyEd25519: verifyEd25519,
    sha256: sha256,
    // §12
    legacyPipeCanonical: legacyPipeCanonical,
    // entry points
    verify: verify,
    verifyAwr2: verifyAwr2,
    verifyBundle: verifyBundle,
    verifyLegacy: function (doc, opts) { return verifyLegacy(doc, withDefaults(opts)); },
    // Backwards-compatible name used by js/renderer.js and by earlier callers.
    verifyProvenanceReceipt: verify
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof root !== 'undefined') {
    root.AWR = API;
    root.AIProvenanceVerifier = API;
  }

})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this));
