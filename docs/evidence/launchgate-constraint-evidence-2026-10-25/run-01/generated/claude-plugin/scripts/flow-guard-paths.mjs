// GENERATED from src/flow-guard-paths.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: where the guard keeps its state, which files are credentials, and which would let the agent switch it off. */
import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, isAbsolute, join, normalize, resolve, sep } from 'node:path';
export function stateDir(env = process.env) {
    return env.WARDEN_STATE_DIR || join(env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'warden');
}
export function sessionKey(sessionId) {
    return createHash('sha256').update(sessionId).digest('hex');
}
export function flowPaths(dir, sessionId) {
    const base = join(dir, 'claude-code', 'flow');
    const key = sessionKey(sessionId);
    return { dir: base, state: join(base, `${key}.json`), fp: join(base, `${key}.fp`), secret: join(base, `${key}.secret.fp`), pii: join(base, `${key}.pii.fp`), tok: join(base, `${key}.tok.fp`), hint: join(base, `${key}.hint.fp`), log: join(base, `${key}.log`) };
}
function expandHome(p) {
    return p === '~' ? homedir() : p.startsWith('~/') ? join(homedir(), p.slice(2)) : p;
}
export function absPath(p, cwd) {
    const e = expandHome(p);
    return normalize(isAbsolute(e) ? e : resolve(cwd, e));
}
// Resolve existing ancestors too: a write to symlink-dir/new-file must protect the real target.
export function physicalPath(p) {
    try {
        return realpathSync(p);
    }
    catch {
        const parent = dirname(p);
        return parent === p ? p : join(physicalPath(parent), basename(p));
    }
}
export function shellPath(p, cwd, env) {
    const expanded = p.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g, (match, braced, plain) => env[braced || plain] ?? match);
    return absPath(expanded.replace(/^['"]|['"]$/g, '').replace(/^@/, ''), cwd);
}
export function inside(child, parent) {
    const p = parent.endsWith(sep) ? parent : parent + sep;
    return child === parent || child.startsWith(p);
}
const SECRET_PATH = /(^|\/)(\.ssh|\.aws|\.gnupg|\.kube|\.docker|\.config\/gh|\.config\/gcloud|\.azure|\.password-store|keychains?)(\/|$)|(^|\/)(\.netrc|\.npmrc|\.pypirc|\.git-credentials|\.pgpass|id_(rsa|dsa|ecdsa|ed25519)[^/]*|[^/]*\.(pem|key|p12|pfx|kdbx|keystore|jks)|\.env(\.[^/]*)?|credentials?(\.[^/]*)?|secrets?(\.[^/]*)?)$/i;
export function isSecretPath(path) {
    return SECRET_PATH.test(path.replace(/\\/g, '/'));
}
export const FOREIGN_DIRS = /(^|\/)(node_modules|vendor|\.venv|venv|site-packages|dist-packages|bower_components|Pods|\.cargo\/registry|go\/pkg\/mod)(\/|$)/;
/** Files that, if the agent could change them, would let it switch the guard off. */
export function isProtectedPath(path, cwd, env = process.env) {
    // join also normalizes a root home: `${home}/...` would produce a double slash
    // for HOME=/ and fail to match the normalized /.claude.json or plugin path.
    const homeConfig = join(homedir(), '.claude.json').replace(/\\/g, '/');
    const homePlugins = join(homedir(), '.claude', 'plugins').replace(/\\/g, '/');
    return [path, physicalPath(path)].some(candidate => {
        const p = candidate.replace(/\\/g, '/');
        if (inside(p, physicalPath(resolve(stateDir(env))).replace(/\\/g, '/')))
            return true;
        if (env.WARDEN_FLOW_POLICY && p === physicalPath(resolve(env.WARDEN_FLOW_POLICY)).replace(/\\/g, '/'))
            return true;
        if (/(^|\/)\.claude\/settings(\.local)?\.json$/.test(p))
            return true;
        if (p === homeConfig || /(^|\/)\.mcp\.json$/.test(p))
            return true;
        if (inside(p, homePlugins) || /(^|\/)\.claude\/hooks(\/|$)/.test(p))
            return true;
        if (/(^|\/)\.git\/(?:config$|hooks(?:\/|$))/.test(p))
            return true;
        if (/(^|\/)warden\.lock\.json$/.test(p) && inside(p, cwd.replace(/\\/g, '/')))
            return true;
        return false;
    });
}
