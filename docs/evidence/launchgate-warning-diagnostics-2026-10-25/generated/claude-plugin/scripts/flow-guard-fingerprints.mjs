// GENERATED from src/flow-guard-fingerprints.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: fingerprints of what the session read (private text, personal numbers, credentials) and the secret formats it knows. */
import { createHash } from 'node:crypto';
import { MAX_TEXT } from './flow-guard-text.mjs';
export const WINDOW = 20;
const STRIDE = 4;
// Credentials are fingerprinted again in short windows of their letters and digits only, so a piece of a key, or the
// key with separators between its characters, is still recognised. The sizes are the smallest at which none of 480
// made-up keys in eight formats matched anywhere in 100 million letters and digits of ordinary text
// (scripts/redteam/window-collisions.mjs): 8 for keys of letters and digits, 10 for hex keys, whose characters carry
// half the information and which share their alphabet with every hash and address in the text around them.
const TOKEN_WINDOW = 8;
const HEX_TOKEN_WINDOW = 10;
export const TOKEN_WINDOWS = [TOKEN_WINDOW, HEX_TOKEN_WINDOW];
const NORMALIZED_CREDENTIAL_PREFIX = /^(?:[rs]k(?:live|test)|skantapi[0-9]+|skant|skproj|sk|gh[pousr]|githubpat|glpat|npm|xox[abprs]|akia|asia|aiza)/;
// Text every key of a kind shares, so it is no piece of any one key: the RSA, EC and signature algorithm
// identifiers of DER keys and certificates, in letters and digits.
export const KEY_STRUCTURE = ['anbgkqhkig9w0baqefaa', 'a0gcsqgsib3dqebcwua', 'a0gcsqgsib3dqebbquaa', 'byqgsm49ageg', 'ccqgsm49aweh', 'bsubbaaiq', 'mcowbqydk2vw', 'mcowbqydk2vu'];
export function normalizeText(s) {
    return s.normalize('NFKC').toLowerCase().replace(/\s+/g, '');
}
export function fpHash(window) {
    return createHash('sha256').update(window).digest('hex').slice(0, 12);
}
/** Windows of the private text at every STRIDE-th position: any leaked run of WINDOW+STRIDE-1 normalized chars hits one. */
export function fingerprints(text) {
    const n = normalizeText(text.slice(0, MAX_TEXT));
    const out = new Set();
    for (let i = 0; i + WINDOW <= n.length; i += STRIDE) {
        const w = n.slice(i, i + WINDOW);
        if (/^(.)\1+$/.test(w) || /^[0-9]+$/.test(w))
            continue;
        out.add(fpHash(w));
    }
    return [...out];
}
// Short structured values a 20-character window misses: card, passport, account and phone numbers.
// Words are split on whitespace; consecutive words that carry digits ("DE89 3704 0044", "+1 (555) 123-4567")
// join into one value, and a word without digits ends it.
const DATE_LIKE = /^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{0,6}$/;
export function piiTokens(text) {
    const out = new Set();
    const flush = (group) => {
        const t = group.join('').replace(/[^a-z0-9]/gi, '').toLowerCase();
        const digits = (t.match(/\d/g) || []).length;
        if (t.length < 8 || t.length > 34 || digits < 5 || DATE_LIKE.test(t))
            return;
        if (/^\d+$/.test(t) && t.length < 9)
            return;
        out.add(t);
    };
    let group = [];
    for (const word of text.slice(0, MAX_TEXT).split(/\s+/)) {
        const bare = word.replace(/^[^A-Za-z0-9+(]+|[^A-Za-z0-9)]+$/g, '');
        if (/\d/.test(bare) && /^[A-Za-z0-9+()./-]+$/.test(bare)) {
            group.push(bare);
            continue;
        }
        if (group.length) {
            flush(group);
            group = [];
        }
    }
    if (group.length)
        flush(group);
    return [...out];
}
const SECRET_PATTERNS = [
    ['private key', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
    ['AWS access key', /\b(AKIA|ASIA)[0-9A-Z]{16}\b/],
    ['GitHub token', /\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}/],
    ['GitLab token', /\bglpat-[A-Za-z0-9_-]{20,}/],
    ['Slack token', /\bxox[abprs]-[A-Za-z0-9-]{10,}/],
    ['npm token', /\bnpm_[A-Za-z0-9]{36}\b/],
    ['API key', /\bsk-(ant-)?[A-Za-z0-9_-]{20,}/],
    ['Google API key', /\bAIza[0-9A-Za-z_-]{35}\b/],
];
export function secretPattern(texts) {
    for (const t of texts)
        for (const [name, re] of SECRET_PATTERNS)
            if (re.test(t))
                return name;
    return undefined;
}
// Cyrillic and Greek letters that look like Latin ones: a key retyped with them is the same key to a reader.
export const CONFUSABLE = {
    а: 'a', в: 'b', е: 'e', ё: 'e', к: 'k', м: 'm', н: 'h', о: 'o', р: 'p', с: 'c', т: 't', у: 'y', х: 'x', і: 'i', ј: 'j', ѕ: 's', ԁ: 'd', ԛ: 'q', ԝ: 'w',
    α: 'a', β: 'b', ε: 'e', η: 'n', ι: 'i', κ: 'k', ν: 'v', ο: 'o', ρ: 'p', τ: 't', υ: 'u', χ: 'x', γ: 'y', ζ: 'z',
};
/** Letters and digits only, lower-cased: separators, case, spacing and look-alike letters do not hide a key. */
export function alnum(s) {
    return s.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g, ch => CONFUSABLE[ch] ?? '');
}
function entropy(s) {
    const counts = new Map();
    for (const ch of s)
        counts.set(ch, (counts.get(ch) ?? 0) + 1);
    let h = 0;
    for (const n of counts.values())
        h -= (n / s.length) * Math.log2(n / s.length);
    return h;
}
const TOKEN_RUN = /[A-Za-z0-9+/_-]{16,}={0,2}/g;
/** Key-like values in private text: every random-looking run of a credential file, and every well-known
 * secret format wherever it was read. Words, paths and host names are not random enough to count. */
export function secretValues(text, credentialFile) {
    const out = new Set();
    const t = text.slice(0, MAX_TEXT);
    const add = (raw) => {
        // A base64 JSON object (a JWT's header or claims) is readable by anyone who holds the token; its signature,
        // the run after the next dot, is the secret part and is kept.
        if (raw.startsWith('eyJ'))
            return;
        const a = alnum(raw);
        if (a.length >= 16 && /\d/.test(a) && /[a-z]/.test(a) && entropy(a) >= 3.5)
            out.add(raw);
    };
    if (credentialFile)
        for (const m of t.matchAll(TOKEN_RUN))
            add(m[0]);
    for (const [, re] of SECRET_PATTERNS)
        for (const m of t.matchAll(new RegExp(re.source, 'g')))
            add(m[0]);
    return [...out];
}
/** Normalized credentials for the original strong-window check. Raw values exist only transiently. */
export function secretTokens(text, credentialFile) {
    return [...new Set(secretValues(text, credentialFile).map(alnum))];
}
/** Known providers' alphabetic payload prefixes are still secret: do not skip them merely because the first
 * digit comes late. Keep every previously indexed window. Generic values retain the old conservative start:
 * public word-based environment values ending in a year must not gain new hard-denial substrings. */
export function tokenFingerprintStart(a) {
    const leading = /^[a-z]*/.exec(a)[0].length;
    if (/^(mii|mig|mhc|mc4|mco)/.test(a))
        return Math.max(48, leading);
    const prefix = NORMALIZED_CREDENTIAL_PREFIX.exec(a)?.[0];
    return prefix ? Math.min(leading, prefix.length) : leading;
}
/** Windows hold both a letter and a digit; alphabetic-only words are not strong credential evidence.
 * Public format/DER structure is excluded. The 8/10-character thresholds and stored hash format are unchanged. */
export function tokenFingerprints(tokens) {
    const out = new Set();
    for (const a of tokens) {
        const size = /^[0-9a-f]+$/.test(a) ? HEX_TOKEN_WINDOW : TOKEN_WINDOW;
        const start = tokenFingerprintStart(a);
        for (let i = start; i + size <= a.length; i++) {
            const w = a.slice(i, i + size);
            if (/\d/.test(w) && /[a-z]/.test(w) && !KEY_STRUCTURE.some(k => k.includes(w)))
                out.add(fpHash(w));
        }
    }
    return [...out];
}
/** Every window of letters and digits of both token sizes, forwards and backwards: what a call is checked by. */
export function tokenWindows(text) {
    const out = [];
    for (const a of [alnum(text), alnum([...text].reverse().join(''))]) {
        for (const size of TOKEN_WINDOWS)
            for (let i = 0; i + size <= a.length; i++)
                out.push(fpHash(a.slice(i, i + size)));
    }
    return out;
}
