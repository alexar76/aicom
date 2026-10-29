// GENERATED from src/flow-guard-fragments.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: short fragments of credentials, kept as hashes only, so a key sent in pieces is still recognised. */
import { createHash } from 'node:crypto';
import { strings } from './flow-guard-text.mjs';
import { CONFUSABLE, KEY_STRUCTURE, alnum } from './flow-guard-fingerprints.mjs';
import { scanCandidates } from './flow-guard-decode.mjs';
const FRAGMENT_SIZE = 6;
export const MAX_FRAGMENT_INDEX = 16_384;
export const MAX_FRAGMENT_SEEN = 256;
const fragmentHash = (s) => createHash('sha256').update(`warden-fragment-v1:${s}`).digest('hex').slice(0, 32);
export const fragmentKey = (r) => `${r.group}:${r.offset}:${r.size ?? FRAGMENT_SIZE}:${r.edge ? 'edge' : 'atom'}:${r.hash}`;
const CREDENTIAL_PREFIX = /^(?:[rs]k_(?:live|test)_|sk-ant-api[0-9]+-|sk-ant-|sk-proj-|sk-|gh[pousr]_|github_pat_|glpat-|npm_|xox[abprs]-|AKIA|ASIA|AIza)/i;
const fragmentVisible = (s) => s.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g, ch => CONFUSABLE[ch] ?? ch);
export const SHORT_SIZES = [5, 6, 7];
/** Weak evidence asks before its first transmission, never silently learns by sending it.
 * Five-char windows require upper/lower/digit classes in the source, while 6/7-char atoms may be words.
 * Exact prefix-boundary slices cover chunks that already contain payload but no full six-char window.
 * Only hash/offset/size metadata is persisted; public format and DER structure alone do not count. */
export function fragmentFingerprints(tokens, limit = MAX_FRAGMENT_INDEX) {
    const out = [];
    for (const raw of new Set(tokens)) {
        const a = alnum(raw), prefix = CREDENTIAL_PREFIX.exec(raw)?.[0];
        const normPrefix = /^(?:[rs]k(?:live|test)|skantapi[0-9]+|skant|skproj|sk|gh[pousr]|githubpat|glpat|npm|xox[abprs]|akia|asia|aiza)/.exec(a)?.[0];
        const start = /^(mii|mig|mhc|mc4|mco)/.test(a) ? Math.max(48, /^[a-z]*/.exec(a)[0].length) : normPrefix?.length ?? /^[a-z]*/.exec(a)[0].length;
        const group = fragmentHash(`key:${a}`);
        // Preserve case only transiently to avoid indexing every short hex/hash or ordinary word.
        const caseful = raw.normalize('NFKC').replace(/[^a-z0-9]/gi, '');
        for (const size of SHORT_SIZES)
            for (let offset = start; offset + size <= a.length; offset++) {
                const piece = a.slice(offset, offset + size), original = caseful.slice(offset, offset + size);
                if (size < FRAGMENT_SIZE && !(/[A-Z]/.test(original) && /[a-z]/.test(original) && /[0-9]/.test(original)))
                    continue;
                if (/^(.)\1+$/.test(piece) || KEY_STRUCTURE.some(k => k.includes(piece)))
                    continue;
                out.push({ group, hash: fragmentHash(piece), offset, size });
                if (out.length > limit)
                    return out;
            }
        if (prefix)
            for (let offset = 0; offset < prefix.length; offset++) {
                // Require a real format delimiter, or the entire delimiter-free prefix (AWS/Google).
                const suffix = prefix.slice(offset);
                if (offset !== 0 && (!/[_-]/.test(suffix) || !/[a-z]/i.test(suffix)))
                    continue;
                for (let length = 1; length <= 7 && prefix.length + length <= raw.length; length++) {
                    const piece = fragmentVisible(raw.slice(offset, prefix.length + length));
                    if (piece.length < 5)
                        continue;
                    out.push({ group, hash: fragmentHash(`edge:${piece}`), offset, size: piece.length, edge: true });
                    if (out.length > limit)
                        return out;
                }
            }
    }
    return out;
}
/** Full isolated atoms, not every substring of long ordinary hashes. Structured encoded candidates are included. */
function fragmentAtoms(input) {
    const hashes = new Set(), scan = scanCandidates(strings(input));
    if (scan.incomplete)
        return { hashes, incomplete: true };
    for (const text of scan.values) {
        const visible = fragmentVisible(text);
        for (const run of visible.matchAll(/\b(?:[a-z0-9][\t ]+){4,6}[a-z0-9]\b/g)) {
            const atom = alnum(run[0]);
            hashes.add(fragmentHash(atom));
            hashes.add(fragmentHash([...atom].reverse().join('')));
        }
        for (const m of visible.matchAll(/[a-z0-9+/_-]+/g)) {
            const raw = m[0];
            if (raw.length <= 64)
                hashes.add(fragmentHash(`edge:${raw}`));
            const joined = alnum(raw);
            if (/^[a-z0-9]{5,7}$/.test(joined)) {
                hashes.add(fragmentHash(joined));
                hashes.add(fragmentHash([...joined].reverse().join('')));
            }
            // Separators delimit atoms; a long uninterrupted hash is never scanned with weak windows.
            for (const atom of raw.matchAll(/[a-z0-9]+/g))
                if (/^[a-z0-9]{5,7}$/.test(atom[0])) {
                    hashes.add(fragmentHash(atom[0]));
                    hashes.add(fragmentHash([...atom[0]].reverse().join('')));
                }
        }
    }
    return { hashes, incomplete: scan.incomplete };
}
/** Must run under the session lock when remembering evidence. Audit never consumes or whitelists a match. */
export function checkFragments(input, state, hasLegacyTokens, remember) {
    const f = state.fragments;
    if (!f)
        return hasLegacyTokens ? { unavailable: true } : {};
    if (f.v !== 2 || f.full)
        return { unavailable: true };
    if (!f.index.length)
        return {};
    const { hashes, incomplete } = fragmentAtoms(input);
    const matches = f.index.filter(r => hashes.has(r.hash));
    if (!matches.length)
        return incomplete ? { unavailable: true } : {};
    const seen = new Map(f.seen.map(r => [fragmentKey(r), r]));
    for (const r of matches)
        seen.set(fragmentKey(r), r);
    const all = [...seen.values()];
    const offsets = new Map();
    for (const r of all) {
        if (r.edge || r.size !== FRAGMENT_SIZE)
            continue;
        const key = `${r.group}:${r.offset}`, at = offsets.get(key) ?? new Set();
        at.add(r.hash);
        offsets.set(key, at);
    }
    const paired = all.some(r => !r.edge && r.size === FRAGMENT_SIZE && [...(offsets.get(`${r.group}:${r.offset + FRAGMENT_SIZE}`) ?? [])].some(h => h !== r.hash));
    if (remember) {
        f.seen = all.slice(0, MAX_FRAGMENT_SEEN);
        if (all.length > MAX_FRAGMENT_SEEN)
            f.full = true;
    }
    if (paired)
        return { secret: 'adjacent short fragments of a credential this session read' };
    return { review: true, ...(incomplete || all.length > MAX_FRAGMENT_SEEN ? { unavailable: true } : {}) };
}
