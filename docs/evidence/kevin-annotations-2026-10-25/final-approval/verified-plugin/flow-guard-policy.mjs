// GENERATED from src/flow-guard-policy.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: the operator's user-level policy, and the exact public requests it may allow after a credential read. */
import { createHash } from 'node:crypto';
import { closeSync, constants, fstatSync, openSync, readFileSync, readSync } from 'node:fs';
import { join } from 'node:path';
import { stateDir } from './flow-guard-paths.mjs';
import { parseGuiPolicy } from './flow-guard-screen.mjs';
export const DEFAULT_POLICY = { mode: 'ask', annotationReview: 'off', labels: {}, trustedSources: [], allowedDestinations: [], taintLocalFiles: false, destinationArgs: {}, answerNote: 'always' };
export const LABELS = ['private', 'untrusted', 'outbound', 'destructive'];
const MODES = ['ask', 'deny', 'audit', 'off'];
const ANSWER_NOTES = ['always', 'instruction', 'off'];
/** User-level policy only (`<state dir>/flow-policy.json`): a project file is something the agent can edit. */
export function loadPolicy(env = process.env) {
    const policy = { ...DEFAULT_POLICY, labels: {}, trustedSources: [], allowedDestinations: [], destinationArgs: {} };
    const path = env.WARDEN_FLOW_POLICY || join(stateDir(env), 'flow-policy.json');
    let raw;
    try {
        raw = JSON.parse(readFileSync(path, 'utf8'));
    }
    catch {
        raw = undefined;
    }
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        const r = raw;
        if (typeof r.mode === 'string' && MODES.includes(r.mode))
            policy.mode = r.mode;
        if (r.annotationReview === 'first-use' || r.annotationReview === 'off')
            policy.annotationReview = r.annotationReview;
        if (r.labels && typeof r.labels === 'object' && !Array.isArray(r.labels)) {
            for (const [k, v] of Object.entries(r.labels)) {
                if (Array.isArray(v))
                    policy.labels[k] = v.filter((x) => LABELS.includes(x));
            }
        }
        if (Array.isArray(r.trustedSources))
            policy.trustedSources = r.trustedSources.map(String);
        if (Array.isArray(r.allowedDestinations))
            policy.allowedDestinations = r.allowedDestinations.map(String);
        if (Array.isArray(r.contactTools))
            policy.contactTools = r.contactTools.filter((v) => typeof v === 'string');
        if (typeof r.taintLocalFiles === 'boolean')
            policy.taintLocalFiles = r.taintLocalFiles;
        if (typeof r.answerNote === 'string' && ANSWER_NOTES.includes(r.answerNote))
            policy.answerNote = r.answerNote;
        if (r.gui !== undefined)
            policy.gui = parseGuiPolicy(r.gui);
        if (r.credentialEgress !== undefined)
            policy.credentialEgress = parseCredentialEgress(r.credentialEgress);
        if (r.taskAdapter !== undefined)
            policy.taskAdapter = parseTaskAdapter(r.taskAdapter);
        if (r.destinationArgs && typeof r.destinationArgs === 'object' && !Array.isArray(r.destinationArgs)) {
            for (const [k, v] of Object.entries(r.destinationArgs))
                if (Array.isArray(v))
                    policy.destinationArgs[k] = v.map(String);
        }
    }
    const mode = env.WARDEN_FLOW_MODE;
    if (mode && MODES.includes(mode))
        policy.mode = mode;
    return policy;
}
function parseTaskAdapter(value) {
    const invalid = { mode: 'strict', server: '', manifestSha256: '', invalid: true };
    if (!value || typeof value !== 'object' || Array.isArray(value))
        return invalid;
    const v = value;
    if (Object.keys(v).some(k => !['mode', 'server', 'manifestSha256'].includes(k)) ||
        v.mode !== undefined && !['strict', 'capabilities', 'review'].includes(v.mode) ||
        typeof v.server !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(v.server) || v.server.includes('__') ||
        typeof v.manifestSha256 !== 'string' || !/^[0-9a-f]{64}$/.test(v.manifestSha256))
        return invalid;
    return { mode: v.mode === 'capabilities' || v.mode === 'review' ? v.mode : 'strict', server: v.server, manifestSha256: v.manifestSha256 };
}
/** Read bounded, pinned operator configuration. The task runtime additionally validates the complete schema. */
export function readPinnedTaskManifest(policy, env = process.env) {
    if (!policy.taskAdapter || policy.taskAdapter.invalid)
        throw new Error('task adapter is not configured');
    const path = join(stateDir(env), 'task-manifest.json');
    const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
        if (!fstatSync(fd).isFile())
            throw new Error('invalid task manifest file');
        const bytes = Buffer.alloc(262_145);
        const count = readSync(fd, bytes, 0, bytes.length, 0);
        if (count > 262_144)
            throw new Error('task manifest is too large');
        const data = bytes.subarray(0, count);
        if (createHash('sha256').update(data).digest('hex') !== policy.taskAdapter.manifestSha256)
            throw new Error('task manifest pin mismatch');
        return new TextDecoder('utf-8', { fatal: true }).decode(data);
    }
    finally {
        closeSync(fd);
    }
}
/** This delegates only fixed control IDs to our own enforcing adapter, never clicks or arbitrary MCP servers.
 * The operator must bind this exact MCP server name to `warden-mcp task`; tool output cannot establish trust. */
export function taskDelegation(tool, args, policy, env) {
    const task = policy.taskAdapter;
    if (policy.mode !== 'ask' || !task || !['capabilities', 'review'].includes(task.mode) || task.invalid)
        return false;
    const prefix = `mcp__${task.server}__`;
    if (!tool.startsWith(prefix))
        return false;
    const action = tool.slice(prefix.length);
    if (action === 'task_list')
        return Object.keys(args).length === 0;
    if (!['task_read', 'task_execute', 'task_run'].includes(action) || task.mode === 'review' && action === 'task_execute' || Object.keys(args).length !== 1 || typeof args.id !== 'string')
        return false;
    try {
        const manifest = JSON.parse(readPinnedTaskManifest(policy, env));
        if (!manifest || manifest.version !== 1 || !Number.isFinite(Date.parse(manifest.expiresAt)) || Date.parse(manifest.expiresAt) <= Date.now())
            return false;
        const entries = action === 'task_read' ? manifest.resources : action === 'task_run' ? manifest.runs : manifest.operations;
        return Array.isArray(entries) && entries.some((entry) => !!entry && typeof entry === 'object' && entry.id === args.id);
    }
    catch {
        return false;
    }
}
function parseCredentialEgress(value) {
    const deny = () => ({ allow: [], invalid: true });
    if (!value || typeof value !== 'object' || Array.isArray(value))
        return deny();
    const v = value;
    if (Object.keys(v).some(k => k !== 'allow') || !Array.isArray(v.allow) || v.allow.length > 32)
        return deny();
    const allow = [];
    for (const raw of v.allow) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw))
            return deny();
        const r = raw;
        if (Object.keys(r).some(k => !['tool', 'requestSha256'].includes(k)) || typeof r.tool !== 'string' ||
            !/^(?:mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_.-]+|WebFetch|WebSearch|Write|Edit|MultiEdit|NotebookEdit)$/.test(r.tool) || r.tool.length > 200 ||
            typeof r.requestSha256 !== 'string' || !/^[0-9a-f]{64}$/.test(r.requestSha256))
            return deny();
        allow.push({ tool: r.tool, requestSha256: r.requestSha256 });
    }
    return { allow };
}
/** Sorted JSON keys; array order and every argument/destination are significant. Never hashes a truncated input. */
export function publicRequestDigest(tool, input) {
    let nodes = 0, chars = 0;
    const encode = (v, depth = 0) => {
        if (++nodes > 1024 || depth > 32)
            throw new Error('request exceeds digest limits');
        let result;
        if (v === null || typeof v === 'boolean' || typeof v === 'string' || typeof v === 'number' && Number.isFinite(v))
            result = JSON.stringify(v);
        else if (Array.isArray(v))
            result = '[' + v.map(x => encode(x, depth + 1)).join(',') + ']';
        else if (v && typeof v === 'object' && [Object.prototype, null].includes(Object.getPrototypeOf(v))) {
            result = '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + encode(v[k], depth + 1)).join(',') + '}';
        }
        else
            throw new Error('request is not JSON');
        chars += result.length;
        if (chars > 65_536 || result.length > 16_384)
            throw new Error('request exceeds digest limits');
        return result;
    };
    try {
        return createHash('sha256').update(encode([tool, input])).digest('hex');
    }
    catch {
        return undefined;
    }
}
export function globMatch(glob, name) {
    const re = new RegExp('^' + glob.split('*').map(s => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*') + '$', 'i');
    return re.test(name);
}
export function hostMatches(host, patterns) {
    const h = host.toLowerCase().replace(/\.$/, '');
    return patterns.some(p => {
        const q = p.toLowerCase().replace(/\.$/, '');
        return q.startsWith('*.') ? h.endsWith(q.slice(1)) && h.length > q.length - 1 : h === q;
    });
}
