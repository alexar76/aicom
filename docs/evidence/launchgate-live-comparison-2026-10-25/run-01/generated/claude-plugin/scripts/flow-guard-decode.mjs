// GENERATED from src/flow-guard-decode.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: reversible spellings a value can hide in (URL, base64, hex, escapes, character lists, NATO), decoded into candidates. */
const MAX_CANDIDATE = 524_288;
/** Only explicit character lists are decoded, never arbitrary prose. Unknown items end a run.
 * English digit names and case markers cover the recorded attack, not arbitrary verbal encodings. */
export function spelledCandidates(text) {
    const digits = { zero: '0', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6', seven: '7', eight: '8', nine: '9' };
    const out = [];
    let run = '';
    const flush = () => { if (run.length >= 5)
        out.push(run); run = ''; };
    for (const item of text.slice(0, MAX_CANDIDATE).normalize('NFKC').split(/[,;|\r\n]+/)) {
        const unit = item.trim().toLowerCase();
        const ch = /^[a-z0-9]$/.test(unit) ? unit : (Object.hasOwn(digits, unit) ? digits[unit] : undefined) ?? /^(?:capital|uppercase|lowercase|letter) ([a-z])$/.exec(unit)?.[1];
        if (ch)
            run += ch;
        else
            flush();
    }
    flush();
    return out;
}
/** Decimal scalar codes, in a contiguous explicit list. Unknown/invalid items terminate a run.
 * Merely decoding public numbers does not block anything: existing secret/private fingerprints still decide. */
export function characterCodeCandidates(text) {
    const out = [];
    let run = '', count = 0;
    const flush = () => { if (count >= 5)
        out.push(run); run = ''; count = 0; };
    for (const item of text.slice(0, MAX_CANDIDATE).normalize('NFKC').split(/[\s,;|[\]]+/)) {
        if (!item)
            continue;
        const code = /^\d{1,7}$/.test(item) ? Number(item) : -1;
        if (code >= 32 && code <= 0x10ffff && !(code >= 0x7f && code <= 0x9f) && !(code >= 0xd800 && code <= 0xdfff) || [9, 10, 13].includes(code)) {
            run += String.fromCodePoint(code);
            count++;
        }
        else
            flush();
    }
    flush();
    return out;
}
const NATO = Object.freeze(Object.fromEntries([
    ...'alfa bravo charlie delta echo foxtrot golf hotel india juliett kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu'.split(' ').map((word, i) => [word, String.fromCharCode(97 + i)]),
    ['alpha', 'a'], ['juliet', 'j'], ['x-ray', 'x'],
    ['niner', '9'],
    ...'zero one two three four five six seven eight nine'.split(' ').map((word, i) => [word, String(i)]),
    ['underscore', '_'], ['hyphen', '-'], ['dash', '-'], ['slash', '/'], ['plus', '+'], ['equals', '='], ['dot', '.'],
]));
/** A small explicit spelling grammar, not a language model. Preserve explicit case for nested base64. */
export function natoCandidates(text) {
    const out = [];
    let run = '', count = 0, marker = '';
    const flush = () => { if (count >= 5)
        out.push(run); run = ''; count = 0; marker = ''; };
    for (const item of text.slice(0, MAX_CANDIDATE).normalize('NFKC').split(/[\s,;|]+/)) {
        if (!item)
            continue;
        const unit = item.toLowerCase();
        if (['capital', 'uppercase', 'lowercase', 'letter'].includes(unit)) {
            if (marker)
                flush();
            marker = unit;
            continue;
        }
        const ch = Object.hasOwn(NATO, unit) ? NATO[unit] : /^\d$/.test(unit) ? unit : undefined;
        if (!ch || marker && !/^[a-z]$/.test(ch)) {
            flush();
            continue;
        }
        run += ['capital', 'uppercase'].includes(marker) ? ch.toUpperCase() : ch;
        count++;
        marker = '';
    }
    flush();
    return out;
}
/** Reversible text encodings only: bounded breadth/depth, no eval or decompression. Exhaustion is explicit. */
export function scanCandidates(texts) {
    const values = [], queue = [];
    const seen = new Set();
    let left = MAX_CANDIDATE, incomplete = false;
    const push = (text, depth) => {
        if (!text || seen.has(text))
            return;
        if (depth > 4 || values.length >= 64 || text.length > left) {
            incomplete = true;
            return;
        }
        seen.add(text);
        left -= text.length;
        values.push(text);
        queue.push({ text, depth });
    };
    for (const text of texts) {
        if (text.length > left) {
            incomplete = true;
            if (left)
                push(text.slice(0, left), 0);
        }
        else
            push(text, 0);
    }
    const utf8 = (bytes) => {
        try {
            const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
            return text && !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(text) ? text : undefined;
        }
        catch {
            return undefined;
        }
    };
    for (let index = 0; index < queue.length; index++) {
        const { text, depth } = queue[index];
        const add = (value) => { if (value && value !== text)
            push(value, depth + 1); };
        if (/%[0-9a-f]{2}/i.test(text)) {
            try {
                add(decodeURIComponent(text.replace(/\+/g, ' ')));
            }
            catch { /* malformed literal, never executable */ }
        }
        for (const value of spelledCandidates(text))
            add(value);
        for (const value of characterCodeCandidates(text))
            add(value);
        for (const value of natoCandidates(text))
            add(value);
        const escaped = text.replace(/\\u\{([0-9a-f]{1,6})\}|\\u([0-9a-f]{4})|\\x([0-9a-f]{2})|&#(?:x([0-9a-f]+)|([0-9]+));/gi, (whole, a, b, c, d, e) => {
            const code = Number.parseInt(a ?? b ?? c ?? d ?? e, e === undefined ? 16 : 10);
            return code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : whole;
        });
        add(escaped);
        for (const m of text.matchAll(/[A-Za-z0-9+/_-]{8,}={0,2}/g)) {
            const normalized = m[0].replace(/-/g, '+').replace(/_/g, '/').replace(/=+$/, '');
            if (normalized.length % 4 === 1)
                continue;
            const bytes = Buffer.from(normalized, 'base64');
            if (bytes.toString('base64').replace(/=+$/, '') === normalized)
                add(utf8(bytes));
        }
        for (const m of text.matchAll(/\b(?:[0-9a-f]{2}){3,}\b/gi))
            add(utf8(Buffer.from(m[0], 'hex')));
    }
    return { values, incomplete };
}
/** Compatibility helper: enforcement uses scanCandidates() so truncation is never mistaken for a clean scan. */
export function candidates(texts) { return scanCandidates(texts).values; }
