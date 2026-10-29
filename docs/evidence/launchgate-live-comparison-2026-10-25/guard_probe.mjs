#!/usr/bin/env node
/** Controlled selection-study adapter: actual published hooks, no model or tool handler. */
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const TOOL = 'mcp__records__get_records';
export const POLICY = Object.freeze({
  mode: 'ask', labels: { [TOOL]: ['untrusted'] }, trustedSources: [],
  allowedDestinations: [], taintLocalFiles: false, destinationArgs: {}, answerNote: 'always',
});
// Exact bytes from the owned, integrity-checked published archive. A version string alone is insufficient.
export const PUBLISHED = Object.freeze({
  packageName: '@aimarket/warden', version: '0.21.0',
  archiveSha256: '5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1',
  files: {
    'package.json': '1305663503d94bf3a5aa23cc965b7331f7d77d401e504be544e778bb36d935b2',
    'dist/flow-guard.js': '8b68cef1add6389941d04b9f7e7b04db836d524faeb1e9afbcdda9e793dfb5d9',
  },
});
const MAX_SESSIONS = 256;
const MAX_LINE_BYTES = 262_144;
const MAX_QUERY_BYTES = 16_384;
const MAX_RESULT_BYTES = 65_536;
const MAX_ANSWER_BYTES = 65_536;
const CWD = '/work/selection-fixture';
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

class ProbeError extends Error {
  constructor(kind) { super(kind); this.kind = kind; }
}
function requireCondition(condition, kind) { if (!condition) throw new ProbeError(kind); }
function requestId(request) {
  const id = request?.id;
  return typeof id === 'string' && id.length <= 200 || typeof id === 'number' && Number.isFinite(id) ? id : null;
}
function validateRequest(request) {
  requireCondition(request && typeof request === 'object' && !Array.isArray(request), 'request-shape');
  requireCondition(request.op === 'prepare' || request.op === 'stop', 'unknown-op');
  requireCondition(typeof request.session === 'string' && request.session.length > 0 &&
    request.session.length <= 200 && request.session.trim() === request.session, 'session');
  const allowed = new Set(request.op === 'prepare'
    ? ['id', 'op', 'session', 'query', 'tool_result'] : ['id', 'op', 'session', 'answer', 'stop_hook_active']);
  requireCondition(Object.keys(request).every(key => allowed.has(key)), 'unknown-field');
  if (request.op === 'prepare') {
    requireCondition(typeof request.query === 'string' && request.query.length > 0 &&
      Buffer.byteLength(request.query) <= MAX_QUERY_BYTES, 'query');
    requireCondition(Object.hasOwn(request, 'tool_result'), 'tool-result');
    let encoded;
    try { encoded = JSON.stringify(request.tool_result); } catch { throw new ProbeError('tool-result'); }
    requireCondition(typeof encoded === 'string' && Buffer.byteLength(encoded) <= MAX_RESULT_BYTES, 'tool-result');
  } else {
    requireCondition(typeof request.answer === 'string' && Buffer.byteLength(request.answer) <= MAX_ANSWER_BYTES, 'answer');
    requireCondition(request.stop_hook_active === undefined || typeof request.stop_hook_active === 'boolean', 'continuation-flag');
  }
}

export async function createProbe({ wardenRoot, stateParent = tmpdir(), runtime = PUBLISHED } = {}) {
  requireCondition(process.platform === 'linux', 'linux-required');
  requireCondition(typeof wardenRoot === 'string' && wardenRoot.length > 0, 'warden-root');
  const root = resolve(wardenRoot);
  const sourceHashes = {};
  for (const [file, expected] of Object.entries(runtime.files)) {
    requireCondition(/^(?:package\.json|dist\/flow-guard(?:-[a-z]+)?\.js)$/.test(file), 'runtime-manifest-path');
    let bytes;
    try { bytes = readFileSync(join(root, file)); } catch { throw new ProbeError('runtime-missing'); }
    sourceHashes[file] = sha256(bytes);
    requireCondition(sourceHashes[file] === expected, 'runtime-integrity');
  }
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  requireCondition(pkg.name === runtime.packageName && pkg.version === runtime.version, 'runtime-version');
  const { runFlowHook } = await import(pathToFileURL(join(root, 'dist/flow-guard.js')).href);
  requireCondition(typeof runFlowHook === 'function', 'runtime-export');
  const ownState = mkdtempSync(join(resolve(stateParent), 'launchgate-selection-hooks-'));
  const sessions = new Map();
  let closed = false;
  const policyBytes = JSON.stringify(POLICY) + '\n';
  const artifact = {
    packageName: pkg.name, packageVersion: pkg.version, kind: runtime.kind ?? 'published-0.21.0-exact-hook',
    knownArchiveSha256: runtime.archiveSha256 ?? null, sourceHashes,
    provenanceScope: 'Exact package.json and dependency-free bundled flow-guard.js bytes; not a check of every extracted archive member.',
    helperSha256: sha256(readFileSync(fileURLToPath(import.meta.url))),
    policySha256: sha256(policyBytes), runtime: { platform: process.platform, node: process.version },
  };
  const status = session => ({
    phase: session.phase, prepared: session.permitted,
    permitted: session.permitted, stopCalls: session.stopCalls, recheckRequested: session.recheckRequested,
    continuationSupplied: session.continuationSupplied,
  });
  function hook(session, event, body, events) {
    const input = { session_id: session.id, cwd: CWD, ...body };
    const raw = runFlowHook(event, JSON.stringify(input), session.env);
    const output = raw ? JSON.parse(raw) : null;
    events.push({ event, input, output });
    return output;
  }
  function dispatch(request) {
    requireCondition(!closed, 'closed');
    validateRequest(request);
    const events = [];
    if (request.op === 'prepare') {
      requireCondition(!sessions.has(request.session), 'duplicate-session');
      requireCondition(sessions.size < MAX_SESSIONS, 'session-limit');
      const directory = join(ownState, sha256(request.session));
      mkdirSync(directory, { mode: 0o700 });
      const policyPath = join(directory, 'flow-policy.json');
      writeFileSync(policyPath, policyBytes, { flag: 'wx', mode: 0o600 });
      const session = {
        id: request.session, phase: 'preparing', permitted: false, stopCalls: 0,
        recheckRequested: false, continuationSupplied: false,
        // Explicit experiment policy; do not inherit a production WARDEN policy or state directory.
        env: { WARDEN_STATE_DIR: directory, WARDEN_FLOW_POLICY: policyPath, WARDEN_FLOW_MODE: 'ask' },
      };
      sessions.set(request.session, session);
      hook(session, 'prompt', { prompt: request.query }, events);
      const pre = hook(session, 'pre', { tool_name: TOOL, tool_input: {} }, events);
      const decision = pre?.hookSpecificOutput?.permissionDecision;
      if (decision === 'ask' || decision === 'deny') {
        session.phase = 'pre-refused';
        return { id: requestId(request), ok: true, op: request.op, session: request.session, tool: TOOL, prepared: false,
          permitted: false, additionalContext: null, hookEvents: events, sessionStatus: status(session),
          artifact, policy: POLICY, scope: 'The simulated read was refused; no post event or model tool transcript is authorized.' };
      }
      requireCondition(decision === undefined || decision === 'allow', 'unexpected-pre-decision');
      const post = hook(session, 'post', { tool_name: TOOL, tool_input: {}, tool_response: request.tool_result }, events);
      session.permitted = true;
      session.phase = 'prepared';
      return { id: requestId(request), ok: true, op: request.op, session: request.session, tool: TOOL, prepared: true,
        permitted: true, additionalContext: post?.hookSpecificOutput?.additionalContext ?? null,
        hookEvents: events, sessionStatus: status(session), artifact, policy: POLICY,
        scope: 'Synthetic read-only fixture through actual hooks; no tool handler, model, payment or network operation executed.' };
    }
    const session = sessions.get(request.session);
    requireCondition(!!session, 'unknown-session');
    requireCondition(session.permitted, 'session-not-permitted');
    const continuation = request.stop_hook_active === true;
    requireCondition(session.stopCalls === 0 && !continuation ||
      session.stopCalls === 1 && session.recheckRequested && continuation, 'stop-sequence');
    const output = hook(session, 'stop', { last_assistant_message: request.answer, stop_hook_active: continuation }, events);
    session.stopCalls += 1;
    if (!continuation) session.recheckRequested = output?.decision === 'block';
    session.continuationSupplied = continuation;
    session.phase = session.recheckRequested && !continuation ? 'awaiting-continuation' : 'complete';
    return { id: requestId(request), ok: true, op: request.op, session: request.session, output,
      hookEvents: events, sessionStatus: status(session), artifact,
      loopBound: 'This study permits one initial Stop and, only when requested, one host-marked continuation. It does not claim an independent persistent counter in the product.' };
  }
  return {
    artifact,
    dispatch(request) {
      try { return dispatch(request); }
      catch (error) { return { id: requestId(request), ok: false, op: request?.op ?? null,
        session: typeof request?.session === 'string' ? request.session : null,
        errorKind: error instanceof ProbeError ? error.kind : 'hook-or-state-error' }; }
    },
    close() { if (!closed) { closed = true; rmSync(ownState, { recursive: true, force: true }); } },
  };
}

export async function main(args = process.argv.slice(2)) {
  requireCondition([2, 4].includes(args.length) && args[0] === '--warden-root' && (args.length === 2 || args[2] === '--runtime-manifest'), 'usage');
  const probe = await createProbe({ wardenRoot: args[1], ...(args.length === 4 ? { runtime: JSON.parse(readFileSync(args[3], 'utf8')) } : {}) });
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const close = () => probe.close();
  process.once('SIGTERM', () => { close(); process.exit(143); });
  process.once('SIGINT', () => { close(); process.exit(130); });
  try {
    for await (const line of lines) {
      if (!line.trim()) continue;
      let result;
      if (Buffer.byteLength(line) > MAX_LINE_BYTES) result = { id: null, ok: false, errorKind: 'line-too-large' };
      else {
        try { result = probe.dispatch(JSON.parse(line)); }
        catch { result = { id: null, ok: false, errorKind: 'invalid-json' }; }
      }
      process.stdout.write(JSON.stringify(result) + '\n');
    }
  } finally { close(); }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch(error => {
    process.stderr.write(JSON.stringify({ ok: false, errorKind: error instanceof ProbeError ? error.kind : 'startup-error' }) + '\n');
    process.exitCode = 1;
  });
}
