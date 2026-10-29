// GENERATED from src/flow-guard-leak.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: an outgoing call's arguments checked against the session's fingerprint stores, within one call and across calls. */
import { readFileSync } from 'node:fs';
import { strings } from './flow-guard-text.mjs';
import { TOKEN_WINDOWS, WINDOW, alnum, fpHash, normalizeText, piiTokens, secretPattern } from './flow-guard-fingerprints.mjs';
import { candidates, scanCandidates } from './flow-guard-decode.mjs';
// Long enough to join the longest personal-data token (34) across two calls.
const ALNUM_TAIL = 33;
function windowsAll(text) {
    const n = normalizeText(text);
    const out = new Set();
    for (let i = 0; i + WINDOW <= n.length; i++)
        out.add(fpHash(n.slice(i, i + WINDOW)));
    return out;
}
function tokenHit(text, tokFp) {
    for (const a of [alnum(text), alnum([...text].reverse().join(''))]) {
        for (const size of TOKEN_WINDOWS)
            for (let i = 0; i + size <= a.length; i++)
                if (tokFp.has(fpHash(a.slice(i, i + size))))
                    return true;
    }
    return false;
}
function windowHit(text, store) {
    if (!store.size)
        return false;
    const value = normalizeText(text);
    for (let i = 0; i + WINDOW <= value.length; i++)
        if (store.has(fpHash(value.slice(i, i + WINDOW))))
            return true;
    return false;
}
export function readFp(path) {
    try {
        const lines = readFileSync(path, 'utf8').split('\n').filter(Boolean);
        if (lines.some(line => !/^[0-9a-f]{12}$/.test(line)))
            throw new Error('invalid fingerprints');
        return new Set(lines);
    }
    catch (err) {
        if (err.code === 'ENOENT')
            return new Set();
        throw new Error('flow fingerprints cannot be read safely');
    }
}
export function readStores(paths) {
    return { secret: readFp(paths.secret), fp: readFp(paths.fp), pii: readFp(paths.pii), tok: readFp(paths.tok) };
}
/** `typed`: what the user typed this session. A value the user typed is theirs to send; it is skipped
 * for ordinary private text, never for secrets. */
export function checkLeak(paths, input, typed = [], stores = readStores(paths)) {
    const all = strings(input);
    const scan = scanCandidates(all);
    const cands = scan.values;
    const typedText = typed.join('\n');
    const own = (s) => { const n = normalizeText(s); return n.length > 0 && typedText.includes(n); };
    const pattern = secretPattern(cands);
    if (pattern)
        return { secret: pattern };
    if (scan.incomplete)
        return { incomplete: true };
    const { secret: secretFp, fp: privateFp, pii: piiFp, tok: tokFp } = stores;
    if (!secretFp.size && !privateFp.size && !tokFp.size && !piiFp.size)
        return {};
    for (const c of cands)
        if (windowHit(c, secretFp))
            return { secret: 'text from a credential file this session read' };
    if (tokFp.size)
        for (const c of cands)
            if (tokenHit(c, tokFp))
                return { secret: 'part of a credential this session read' };
    const privateCands = candidates(all.filter(s => !own(s)));
    const result = {};
    if (piiFp.size)
        for (const c of privateCands)
            for (const t of piiTokens(c))
                if (piiFp.has(fpHash(t))) {
                    result.pii = true;
                    break;
                }
    if (privateFp.size)
        for (const c of privateCands)
            if (windowHit(c, privateFp)) {
                result.private = true;
                break;
            }
    return result;
}
/**
 * A value sent in pieces, one call each, is checked whole: each argument name keeps the tail of what it carried,
 * and the windows that cross from that tail into this call are checked like any other. Only pieces sent back to back
 * through the same argument join; words between them break the run. Returns the new tails.
 */
export function checkStream(input, tails, stores) {
    const leak = {};
    const next = {};
    for (const [key, value] of Object.entries(input)) {
        const n = normalizeText(strings(value).join(''));
        if (!n)
            continue;
        const a = alnum(n);
        const prev = tails[key] ?? { t: '', a: '' };
        if (prev.t) {
            for (const h of windowsAll(prev.t + n.slice(0, WINDOW - 1))) {
                if (stores.secret.has(h))
                    leak.secret = 'text from a credential file this session read, sent in pieces';
                if (stores.fp.has(h))
                    leak.private = true;
            }
        }
        if (prev.a) {
            for (const size of TOKEN_WINDOWS) {
                const tok = prev.a.slice(-(size - 1)) + a.slice(0, size - 1);
                for (let i = 0; i + size <= tok.length; i++)
                    if (stores.tok.has(fpHash(tok.slice(i, i + size))))
                        leak.secret = 'part of a credential this session read, sent in pieces';
            }
            if (stores.pii.size) {
                // Personal-data tokens are 8-34 letters and digits: try every one that starts before this call and ends in it.
                const joined = prev.a + a.slice(0, ALNUM_TAIL);
                for (let i = 0; i < prev.a.length && !leak.pii; i++) {
                    for (let len = 8; len <= 34 && i + len <= joined.length; len++) {
                        if (i + len > prev.a.length && stores.pii.has(fpHash(joined.slice(i, i + len)))) {
                            leak.pii = true;
                            break;
                        }
                    }
                }
            }
        }
        next[key] = { t: (prev.t + n).slice(-(WINDOW - 1)), a: (prev.a + a).slice(-ALNUM_TAIL) };
    }
    return { leak, next };
}
