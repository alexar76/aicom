/**
 * RFC 8785 (JSON Canonicalization Scheme) as profiled by AWR/2 (`awr/SPEC.md` §4).
 *
 * Two places in WARDEN turn a JSON value into bytes that a *different*
 * implementation has to reproduce exactly: the signed threat feed (a publisher
 * signs, ARGUS verifies) and the tool-def pin (a sha256 quoted in receipts and
 * re-checked by `argus verify`). `JSON.stringify` cannot do that job — its output
 * depends on the key order the wire happened to use, so one logical document
 * serialises to different bytes on the two sides and the signature fails for no
 * security reason at all.
 *
 * The profile implemented here, rule by rule:
 *
 * 1. **Property names sort as arrays of UTF-16 code units** (RFC 8785 §3.2.3).
 *    JavaScript's default `Array.prototype.sort()` on strings compares exactly
 *    that, so this is the one rule the platform gives away for free.
 *    `String.prototype.localeCompare` does *not*: it depends on the host locale
 *    and ICU version, which makes it unusable as a digest input.
 * 2. **No Unicode normalization, ever** (SPEC §4.1 item 2). NFC would collide two
 *    property names that RFC 8785 keeps distinct.
 * 3. **Two-character escapes plus lowercase `\uXXXX` for the remaining C0
 *    controls** (§3.2.2.2) — which is precisely what `JSON.stringify` emits for a
 *    string, so string bodies are delegated to it rather than re-implemented.
 * 4. **Lone surrogates terminate with an error** instead of being substituted
 *    (§4.1 item 4). `JSON.stringify` would quietly escape them into
 *    valid-looking bytes, so they are rejected before it is called.
 * 5. **Integers only, within ±(2^53−1)**; every non-integer number is refused
 *    rather than arbitrated (§4.3), because whether `1` parses as an integer or
 *    as a double is a language accident that silently changes the signed bytes.
 *
 * Scope: this module is *only* the byte-level canonicalization. It knows nothing
 * about AWR documents, Data Integrity proofs, `did:key` or profiles.
 */
/**
 * A value could not be canonicalized (or parsed) under the AWR profile.
 *
 * Callers are expected to *handle* this rather than let it escape: refusing to
 * produce bytes is the honest outcome, but it must not crash a connection check.
 */
export class CanonicalizationError extends Error {
    code;
    constructor(code, detail) {
        super(`${code}: ${detail}`);
        this.code = code;
        this.name = "CanonicalizationError";
    }
}
/** Largest magnitude of a JSON integer permitted in canonical bytes (2^53−1). */
export const MAX_SAFE_JSON_INTEGER = 9007199254740991;
/**
 * Nesting bound. Canonicalization runs over attacker-influenced input (a remote
 * feed, a third-party tool schema), and an unbounded recursive walk is a
 * denial-of-service (SPEC §13.4).
 */
const MAX_DEPTH = 64;
/**
 * Return the RFC 8785 canonical serialization of `value` as a UTF-8-ready string.
 *
 * Throws {@link CanonicalizationError} rather than emitting bytes it cannot
 * defend: a non-integer number, an integer beyond 2^53−1, a lone surrogate, an
 * `undefined` property (which `JSON.stringify` would silently drop), a
 * non-plain object, or a cycle.
 */
export function canonicalize(value) {
    const out = [];
    serialize(value, out, "$", 0, new Set(), serializeNumber);
    return out.join("");
}
/**
 * Plain RFC 8785, outside the AWR profile: the same bytes as {@link canonicalize}
 * wherever that succeeds, and every other finite number in the ECMAScript form
 * RFC 8785 §3.2.2.3 specifies (`0.7`, `1e+21`). For a host's OWN comparisons — a
 * pin it took and re-checks itself — where the profile's cross-language concern
 * does not arise. Never for bytes another implementation must reproduce.
 */
export function canonicalizeRfc8785(value) {
    const out = [];
    serialize(value, out, "$", 0, new Set(), serializeEs6Number);
    return out.join("");
}
function serialize(value, out, path, depth, seen, num) {
    if (depth > MAX_DEPTH) {
        throw new CanonicalizationError("AWR-CANON-005", `nesting deeper than ${MAX_DEPTH} at ${path}`);
    }
    if (value === null) {
        out.push("null");
        return;
    }
    switch (typeof value) {
        case "boolean":
            out.push(value ? "true" : "false");
            return;
        case "number":
            out.push(num(value, path));
            return;
        case "string":
            out.push(serializeString(value, path));
            return;
        case "object":
            break;
        default:
            // undefined, function, symbol, bigint: JSON has no representation, and
            // guessing one (JSON.stringify drops or throws depending on position) is
            // exactly the silent divergence this module exists to prevent.
            throw new CanonicalizationError("AWR-CANON-005", `${typeof value} at ${path} is not representable in JSON`);
    }
    const obj = value;
    if (seen.has(obj))
        throw new CanonicalizationError("AWR-CANON-005", `circular reference at ${path}`);
    seen.add(obj);
    try {
        if (Array.isArray(obj)) {
            out.push("[");
            for (let i = 0; i < obj.length; i++) {
                if (i > 0)
                    out.push(",");
                serialize(obj[i], out, `${path}[${i}]`, depth + 1, seen, num);
            }
            out.push("]");
            return;
        }
        // Only plain records canonicalize. A Date, Map, RegExp or class instance has
        // no JSON form of its own; `JSON.stringify` would call `toJSON()` or emit
        // `{}`, inventing bytes the other implementation cannot reproduce.
        const proto = Object.getPrototypeOf(obj);
        if (proto !== Object.prototype && proto !== null) {
            throw new CanonicalizationError("AWR-CANON-005", `${obj.constructor?.name ?? "object"} at ${path} is not a plain JSON object`);
        }
        const record = obj;
        out.push("{");
        let first = true;
        // §3.2.3: sort as arrays of UTF-16 code units — the default string sort.
        for (const key of Object.keys(record).sort()) {
            const member = record[key];
            if (member === undefined) {
                throw new CanonicalizationError("AWR-CANON-005", `property "${key}" at ${path} is undefined — JSON has no such value ` +
                    `(JSON.stringify would drop it silently, changing the signed bytes)`);
            }
            if (!first)
                out.push(",");
            first = false;
            out.push(serializeString(key, `property name "${key}" at ${path}`), ":");
            serialize(member, out, `${path}.${key}`, depth + 1, seen, num);
        }
        out.push("}");
    }
    finally {
        seen.delete(obj);
    }
}
/** §4.3: integers only, `[-(2^53-1), 2^53-1]`. Everything else is refused. */
function serializeNumber(n, path) {
    if (!Number.isFinite(n)) {
        throw new CanonicalizationError("AWR-CANON-001", `${String(n)} at ${path} is not a JSON number`);
    }
    if (!Number.isInteger(n)) {
        throw new CanonicalizationError("AWR-CANON-001", `non-integer JSON number ${n} at ${path}`);
    }
    if (!Number.isSafeInteger(n)) {
        throw new CanonicalizationError("AWR-CANON-002", `integer ${n} at ${path} is outside ±(2^53−1)`);
    }
    // Safe integers never render in exponential form, and `String(-0)` is "0".
    return String(n);
}
/** RFC 8785 §3.2.2.3: any finite number, in ECMAScript `Number.prototype.toString` form. */
function serializeEs6Number(n, path) {
    if (!Number.isFinite(n)) {
        throw new CanonicalizationError("AWR-CANON-001", `${String(n)} at ${path} is not a JSON number`);
    }
    // JSON.stringify emits that form, and "0" for -0.
    return JSON.stringify(n);
}
/**
 * §3.2.2.2 string serialization, delegated to `JSON.stringify` — which emits the
 * same two-character escapes and the same lowercase `\u00xx` for the remaining C0
 * controls, and leaves every other character literal. The one divergence is lone
 * surrogates, which it escapes and RFC 8785 forbids, so those are rejected first.
 */
function serializeString(text, path) {
    assertWellFormed(text, path);
    return JSON.stringify(text);
}
/** §4.1 item 4 / `AWR-CANON-003`: unpaired surrogates are an error, not a substitution. */
function assertWellFormed(text, path) {
    for (let i = 0; i < text.length; i++) {
        const unit = text.charCodeAt(i);
        if (unit >= 0xd800 && unit <= 0xdbff) {
            const low = text.charCodeAt(i + 1);
            if (!(low >= 0xdc00 && low <= 0xdfff)) {
                throw new CanonicalizationError("AWR-CANON-003", `lone high surrogate U+${unit.toString(16).toUpperCase()} at index ${i} in ${path}`);
            }
            i++;
        }
        else if (unit >= 0xdc00 && unit <= 0xdfff) {
            throw new CanonicalizationError("AWR-CANON-003", `lone low surrogate U+${unit.toString(16).toUpperCase()} at index ${i} in ${path}`);
        }
    }
}
/**
 * Parse JSON with the profile's parser requirements, for input whose bytes were
 * signed by someone else.
 *
 * `JSON.parse` alone is not enough on a verification path:
 *
 * - **Duplicate property names** (§4.1 item 5, `AWR-CANON-004`) are resolved
 *   last-wins and silently, which would let the parser — not the signer — decide
 *   which of two records was the signed one.
 * - **Non-integer number literals** (§4.3, `AWR-CANON-001`) are rejected
 *   *lexically*, not by value: `2340.0` and `2340` parse to the same JavaScript
 *   number, and a publisher written in a language that distinguishes them would
 *   have signed different bytes.
 *
 * Both checks run over the received text after `JSON.parse` has confirmed it is
 * well-formed, so the scanner below only has to find tokens, never validate
 * grammar.
 */
export function parseJsonStrict(text) {
    let value;
    try {
        value = JSON.parse(text);
    }
    catch (err) {
        throw new CanonicalizationError("AWR-CANON-005", `not well-formed JSON: ${err.message}`);
    }
    auditTokens(text);
    return value;
}
function auditTokens(text) {
    const tokens = tokenize(text);
    for (const token of tokens) {
        if (token.kind === "number")
            assertIntegerLiteral(token.literal);
    }
    // A string immediately followed by `:` inside an object is a property name;
    // in well-formed JSON nothing else can occupy that position.
    const stack = [];
    for (let i = 0; i < tokens.length; i++) {
        const token = tokens[i];
        if (token.kind === "{")
            stack.push(new Set());
        else if (token.kind === "[")
            stack.push(null);
        else if (token.kind === "}" || token.kind === "]")
            stack.pop();
        else if (token.kind === "string") {
            const names = stack[stack.length - 1];
            if (names && tokens[i + 1]?.kind === ":") {
                if (names.has(token.value)) {
                    throw new CanonicalizationError("AWR-CANON-004", `duplicate object property name "${token.value}"`);
                }
                names.add(token.value);
            }
        }
    }
}
function tokenize(text) {
    const tokens = [];
    let i = 0;
    while (i < text.length) {
        const ch = text[i];
        if (ch === '"') {
            const start = i;
            i++;
            while (i < text.length) {
                const c = text[i];
                if (c === "\\") {
                    i += 2;
                    continue;
                }
                i++;
                if (c === '"')
                    break;
            }
            // The slice is a valid JSON string literal (JSON.parse already accepted the
            // whole document), so decoding it cannot fail — and decoding is required:
            // "a" and "a" are the same property name.
            tokens.push({ kind: "string", value: JSON.parse(text.slice(start, i)) });
            continue;
        }
        if (ch === "{" || ch === "}" || ch === "[" || ch === "]" || ch === ":" || ch === ",") {
            tokens.push({ kind: ch });
            i++;
            continue;
        }
        if (ch === "-" || (ch >= "0" && ch <= "9")) {
            const start = i;
            i++;
            while (i < text.length && /[0-9eE+.\-]/.test(text[i]))
                i++;
            tokens.push({ kind: "number", literal: text.slice(start, i) });
            continue;
        }
        // Whitespace and the letters of true/false/null carry nothing we check.
        i++;
    }
    return tokens;
}
function assertIntegerLiteral(literal) {
    if (/[.eE]/.test(literal)) {
        throw new CanonicalizationError("AWR-CANON-001", `non-integer JSON number literal ${literal}`);
    }
    // BigInt, not Number: a 20-digit literal loses precision before it can be
    // compared, and would slip through as a "safe" integer.
    let asInt;
    try {
        asInt = BigInt(literal);
    }
    catch {
        throw new CanonicalizationError("AWR-CANON-005", `malformed number literal ${literal}`);
    }
    const limit = BigInt(MAX_SAFE_JSON_INTEGER);
    if (asInt > limit || asInt < -limit) {
        throw new CanonicalizationError("AWR-CANON-002", `integer literal ${literal} is outside ±(2^53−1)`);
    }
}
//# sourceMappingURL=jcs.js.map