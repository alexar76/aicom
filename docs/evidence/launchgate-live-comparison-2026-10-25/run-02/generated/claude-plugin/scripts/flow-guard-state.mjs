// GENERATED from src/flow-guard-state.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: per-session state under a lock, fingerprint files and the session log. */
import { appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { flowPaths, stateDir, sessionKey } from './flow-guard-paths.mjs';
import { MAX_TEXT } from './flow-guard-text.mjs';
import { secretPattern } from './flow-guard-fingerprints.mjs';
import { MAX_FRAGMENT_INDEX, MAX_FRAGMENT_SEEN, SHORT_SIZES } from './flow-guard-fragments.mjs';
const MAX_SOURCES = 20;
const MAX_PRIVATE = 50;
const MAX_FP_BYTES = 32 * 1_048_576;
export const EMPTY = { v: 1, untrusted: [], private: [], notified: false, full: false };
export function readFlowState(path) {
    try {
        const s = JSON.parse(readFileSync(path, 'utf8'));
        if (!s || s.v !== 1 || !Array.isArray(s.untrusted) || !Array.isArray(s.private))
            throw new Error('invalid flow state');
        if (s.credentialRead !== undefined && s.credentialRead !== true || s.credentialGrants !== undefined && (!Array.isArray(s.credentialGrants) || s.credentialGrants.length > 32 || !s.credentialGrants.every(v => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v))))
            throw new Error('invalid credential egress state');
        if (s.fragments !== undefined) {
            const f = s.fragments;
            if (!f || ![1, 2].includes(f.v))
                throw new Error('invalid fragment state');
            const valid = (r) => {
                if (!r || typeof r.group !== 'string' || !/^[0-9a-f]{32}$/.test(r.group) || typeof r.hash !== 'string' || !/^[0-9a-f]{32}$/.test(r.hash) ||
                    !Number.isSafeInteger(r.offset) || r.offset < 0 || r.offset > MAX_TEXT || r.edge !== undefined && r.edge !== true)
                    return false;
                if (f.v === 1)
                    return r.size === undefined || Number.isSafeInteger(r.size) && r.size >= 1 && r.size <= 64;
                return typeof r.size === 'number' && Number.isSafeInteger(r.size) && (r.edge ? r.size >= 5 && r.size <= 64 : SHORT_SIZES.includes(r.size));
            };
            if (!Array.isArray(f.index) || f.index.length > MAX_FRAGMENT_INDEX || !f.index.every(valid) ||
                !Array.isArray(f.seen) || f.seen.length > MAX_FRAGMENT_SEEN || !f.seen.every(valid) || f.full !== undefined && f.full !== true)
                throw new Error('invalid fragment state');
        }
        return s;
    }
    catch (err) {
        if (err.code === 'ENOENT')
            return { ...EMPTY, untrusted: [], private: [] };
        throw new Error('flow state cannot be read safely');
    }
}
function withLock(path, action) {
    const lock = `${path}.lock`;
    let fd;
    const deadline = Date.now() + 3000;
    while (fd === undefined) {
        try {
            fd = openSync(lock, 'wx', 0o600);
        }
        catch (err) {
            if (err.code !== 'EEXIST')
                throw err;
            // A lock older than 10 s is a crashed hook: take it over rather than wedge the session.
            try {
                if (Date.now() - statSync(lock).mtimeMs > 10_000)
                    unlinkSync(lock);
            }
            catch { /* raced */ }
            if (Date.now() > deadline)
                throw new Error('flow state is locked');
            const until = Date.now() + 15;
            while (Date.now() < until) { /* short spin; hooks are short-lived */ }
        }
    }
    try {
        return action();
    }
    finally {
        closeSync(fd);
        try {
            unlinkSync(lock);
        }
        catch { /* gone */ }
    }
}
function writeAtomic(path, value) {
    const temp = `${path}.${process.pid}.${Date.now()}.tmp`;
    writeFileSync(temp, JSON.stringify(value), { mode: 0o600 });
    renameSync(temp, path);
}
export function updateFlowState(path, change) {
    return withLock(path, () => {
        const s = readFlowState(path);
        change(s);
        s.untrusted = s.untrusted.slice(-MAX_SOURCES);
        s.private = s.private.slice(-MAX_PRIVATE);
        writeAtomic(path, s);
        return s;
    });
}
export function appendFp(path, fps) {
    if (!fps.length)
        return true;
    let size = 0;
    try {
        size = statSync(path).size;
    }
    catch { /* new */ }
    if (size > MAX_FP_BYTES)
        return false;
    appendFileSync(path, fps.join('\n') + '\n', { mode: 0o600 });
    return true;
}
export function log(paths, entry) {
    try {
        mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
        appendFileSync(paths.log, JSON.stringify({ at: new Date().toISOString(), ...entry }) + '\n', { mode: 0o600 });
    }
    catch { /* best effort */ }
}
export function safeToolName(name) {
    return /^[A-Za-z0-9_.:-]{1,100}$/.test(name) && !secretPattern([name]) ? name : '[unrecognized tool name]';
}
/** Display correlation only, never a pin or authority. No server-authored words. */
export function warningSourceId(name) {
    return `source-${sessionKey(name).slice(0, 16)}`;
}
export function flowStateExists(sessionId, env = process.env) {
    return existsSync(flowPaths(stateDir(env), sessionId).state);
}
