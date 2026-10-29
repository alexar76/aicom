import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { constants } from 'node:os';
import { Warden, FilePinStore, pinToolsHash, displaySafe, StaticScanGate, isSensitiveTool } from './index.js';
import type { ToolDef, WardenVerdict } from './types.js';
import { WrapFrames, readFrames } from './wrap-wire.js';
import { loadWrapFeed, wrapLogger, wrapServer, type WrapOptions } from './wrap-cli.js';
import { observe, observedServerInfo, vetAndPin, observationPath, WardenBlock, type Observation } from './wrap-state.js';
import { readState } from './state.js';
import { listAllTools } from './tool-list.js';
import { screenResult, annotateResult } from './result-screen.js';
import { flowPre, flowPost, flowApproval, flowScreenValidation, screenCall, screenResponseStamp, screenObservation, loadPolicy } from './flow-guard.js';
import { screenLease } from './wrap-screen.js';
import { ATOMIC_SCREEN_PROTOCOL, ATOMIC_SCREEN_PREPARE, ATOMIC_SCREEN_COMMIT, ATOMIC_SCREEN_CANCEL, atomicScreenPrepared, atomicScreenReceipt, type AtomicScreenPrepared } from './atomic-screen.js';
import { annotationReview } from './annotation-review.js';

type Message = { jsonrpc: '2.0'; id?: string | number | null; method?: string; params?: Record<string, unknown>; result?: any; error?: unknown };
// How long a call waits for a person to answer the approval form before it is refused.
const ASK_TIMEOUT_MS = 5 * 60_000;
type Answer = 'approved' | 'declined' | 'cancelled' | 'timeout' | 'closed' | 'error';
/** The client cancelled a call before it was sent on: it gets no reply (MCP cancellation). */
class CallCancelled extends Error {}
function parse(body: string): Message {
  const msg = JSON.parse(body);
  if (!msg || Array.isArray(msg) || msg.jsonrpc !== '2.0' ||
      (msg.id !== undefined && msg.id !== null && typeof msg.id !== 'string' && typeof msg.id !== 'number')) throw new Error('Invalid JSON-RPC message');
  return msg;
}

export async function runWrap(opts: WrapOptions): Promise<number> {
  if (opts.screenAtomic && (!opts.flow || !opts.screenRead || opts.auditOnly || !screenObservation(`mcp__${opts.flow}__${opts.screenRead}`, opts.screenReadInput ?? {}))) throw new Error('Atomic screen requires an explicit observation and enforcing flow proxy');
  const server = wrapServer(opts), log = wrapLogger(opts.auditOnly);
  const feed = await loadWrapFeed(opts), store = new FilePinStore(join(opts.stateDir, 'pins'));
  const warden = Warden.create({ policy: opts.policy, threatFeed: feed, store });
  if (opts.verdictLog) mkdirSync(dirname(opts.verdictLog), { recursive: true, mode: 0o700 });
  const record = (verdict: WardenVerdict) => {
    process.stderr.write(`warden: ${opts.auditOnly ? 'AUDIT-ONLY ' : ''}${verdict.allow ? 'ALLOW' : 'BLOCK'} ${displaySafe(server.id)} decidedBy=${displaySafe(verdict.decidedBy ?? '-')} score=${verdict.score.toFixed(2)} ${verdict.findings.map(f => `${displaySafe(f.code)}${f.tool ? `(${displaySafe(f.tool)})` : ''}`).join(' ')}\n`);
    if (opts.verdictLog) appendFileSync(opts.verdictLog, JSON.stringify({ timestamp: new Date().toISOString(), serverId: server.id,
      mode: opts.auditOnly ? 'AUDIT-ONLY' : 'ENFORCE', ...verdict }) + '\n', { mode: 0o600 });
  };
  const launch = await warden.vetLaunch(server); record(launch);
  const prior = await readState<Observation>(observationPath(opts.stateDir, server.id));
  const blockedLaunch = !opts.auditOnly && (!launch.allow || prior?.revoked);
  if (blockedLaunch) await observe(opts.stateDir, { server, policy: opts.policy });
  const reason = (v: WardenVerdict) => `blocked by WARDEN: ${v.findings.filter(f => !f.advisory).map(f => f.code).join(', ')}; warden-mcp pins status --id ${server.id}`;
  const frames = new WrapFrames();
  let child: ChildProcessWithoutNullStreams | undefined;
  let finished = false, closing = false, generation = 0, quarantined = true;
  // Why tools are withheld: a WARDEN decision or a change waits for the client to list again;
  // a check that merely failed to run (timeout, lock, child error) is retried by the next call.
  let quarantineKind: 'start' | 'changed' | 'blocked' | 'error' = 'start';
  let blockReason = blockedLaunch ? (prior?.revoked ? 'Approval revoked; run warden-mcp pins status --id ' + server.id : reason(launch)) : '';
  let visible: ToolDef[] = [];
  let refresh: Promise<ToolDef[]> | undefined;
  const prefix = `warden:${randomUUID()}:`;
  let seq = 0;
  const pending = new Map<string, { resolve: (value: { result: any; bytes: number }) => void; reject: (e: Error) => void; timer: NodeJS.Timeout; screen?: true }>();
  // Every client request forwarded to the child, by id. A child response is delivered only
  // against one of these, once: a response to an id the client never sent to the child (its
  // tools/list, which this proxy answers) or already received is a forgery, not a reply.
  const tracked = new Map<string | number | null, { kind: 'initialize' | 'call' | 'other'; generation: number; tool?: string; args?: Record<string, unknown>; screenRelease?: (abandon?: boolean) => void; atomic?: AtomicScreenPrepared }>();
  // Flow guard (--flow NAME). Every server a client wraps shares one session — by default the client's
  // process, which started them all — so outside text read through one server taints a send through another.
  const flowSession = opts.flow ? (process.env.WARDEN_FLOW_SESSION || `wrap-${process.ppid}`) : '';
  const flowTool = (tool: string) => `mcp__${opts.flow}__${tool}`;
  // Local to this child connection, never a persisted allowlist or a replacement for per-call guards.
  const reviewedAnnotations = new Set<string>();
  let activeChecks = 0;
  // What the client said it can do in its initialize request: `elicitation` is how this proxy asks a person.
  let clientCapabilities: Record<string, unknown> = {};
  // Reported by this connection's child, shown in review separately from tool/launch hashes.
  let serverInfo: Observation['serverInfo'];
  // Questions this proxy put to the client (elicitation/create), by their reserved ids, and the calls that are not
  // sent on yet, by the client's ids: a cancelled one must never reach the child.
  const questions = new Map<string, { resolve: (answer: Answer) => void; timer: NodeJS.Timeout }>();
  const waiting = new Map<string | number | null, { cancelled: boolean; question?: string }>();
  let stopTimer: NodeJS.Timeout | undefined, killTimer: NodeJS.Timeout | undefined;

  return new Promise<number>(resolve => {
    const finish = (code: number) => {
      if (finished) return;
      finished = true;
      clearTimeout(stopTimer); clearTimeout(killTimer);
      for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('MCP child exited')); }
      pending.clear();
      for (const q of questions.values()) { clearTimeout(q.timer); q.resolve('closed'); }
      questions.clear();
      for (const request of tracked.values()) {
        if (request.screenRelease) flowScreenValidation({ session_id: flowSession, tool_name: flowTool(request.tool ?? '') }, 'execution_uncertain');
        try { request.screenRelease?.(true); } catch { /* uncertain effect: keep the lease file */ }
      }
      tracked.clear();
      process.stdin.pause();
      process.removeListener('SIGTERM', signalStop); process.removeListener('SIGINT', signalStop);
      resolve(code);
    };
    const stop = () => {
      if (closing) return;
      closing = true; quarantined = true; generation++;
      if (!child) { finish(blockedLaunch ? 3 : 0); return; }
      child.stdin.end();
      stopTimer = setTimeout(() => child?.kill('SIGTERM'), 5000);
      killTimer = setTimeout(() => child?.kill('SIGKILL'), 9900);
    };
    const signalStop = () => stop();
    const fatal = (error: unknown) => { log.error(error instanceof Error ? error.message : String(error)); stop(); };
    const clientWrite = (body: string) => {
      if (finished) return;
      const data = frames.mode === 'lsp' ? `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}` : body + '\n';
      if (!process.stdout.write(data)) {
        child?.stdout.pause();
        process.stdout.once('drain', () => child?.stdout.resume());
      }
    };
    const send = (msg: object) => clientWrite(JSON.stringify(msg));
    const fail = (msg: Message, message: string, code = -32602) => {
      if (msg.id !== undefined) send({ jsonrpc: '2.0', id: msg.id, error: { code, message: displaySafe(message, 8192) } });
    };
    // The form is MCP elicitation. Since 2025-11-25 a client may offer only `url` mode; an empty object still means form.
    const canAsk = () => {
      const e = clientCapabilities.elicitation;
      return opts.ask === 'elicit' && !!e && typeof e === 'object' && !Array.isArray(e) && (Object.keys(e).length === 0 || 'form' in e);
    };
    const cannotAsk = () => opts.ask === 'refuse' ? ' (--ask refuse)' : ' (this client offers no MCP elicitation form)';
    const withdraw = (id: string, reason: string) => send({ jsonrpc: '2.0', method: 'notifications/cancelled', params: { requestId: id, reason } });
    const answer = (id: string, outcome: Answer) => {
      const q = questions.get(id);
      if (!q) return;
      questions.delete(id); clearTimeout(q.timer); q.resolve(outcome);
    };
    // One question per call. The checkbox defaults to off, so a client that accepts forms with their defaults
    // (no person looking) cannot approve anything.
    const askPerson = (callId: string | number | null, tool: string, args: Record<string, unknown>, reasons: string[]) => new Promise<Answer>(resolveAnswer => {
      const id = `${prefix}ask:${seq++}`;
      const timer = setTimeout(() => { answer(id, 'timeout'); withdraw(id, 'no answer within 5 minutes'); }, ASK_TIMEOUT_MS);
      questions.set(id, { resolve: resolveAnswer, timer });
      const wait = waiting.get(callId);
      if (wait) wait.question = id;
      send({ jsonrpc: '2.0', id, method: 'elicitation/create', params: {
        message: `WARDEN asks before ${displaySafe(tool, 200)} on ${displaySafe(server.id, 200)} runs.\n${reasons.join('\n')}\n` +
          `Arguments: ${displaySafe(JSON.stringify(args), 1500)}\nTick "Run it" and accept to let this one call through; anything else refuses it.`,
        requestedSchema: { type: 'object', required: ['run'], properties: {
          run: { type: 'boolean', title: 'Run it', description: `Run ${displaySafe(tool, 200)} once, with the arguments shown`, default: false } } } } });
    });
    const childWrite = (body: string) => {
      if (!child || closing || finished || child.stdin.destroyed) throw new Error('MCP child unavailable');
      if (!child.stdin.write(body + '\n')) {
        process.stdin.pause();
        child.stdin.once('drain', () => { if (!closing) process.stdin.resume(); });
      }
    };
    const requestPage = (cursor?: string): Promise<{ result: any; bytes: number }> => new Promise((resolvePage, reject) => {
      const id = prefix + seq++;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('MCP tools/list timed out')); }, 10_000);
      pending.set(id, { resolve: resolvePage, reject, timer });
      try { childWrite(JSON.stringify({ jsonrpc: '2.0', id, method: 'tools/list', params: cursor === undefined ? {} : { cursor } })); }
      catch (e) { clearTimeout(timer); pending.delete(id); reject(e); }
    });
    const requestScreen = (): Promise<{ result: any; bytes: number }> => new Promise((resolveScreen, reject) => {
      const id = prefix + seq++;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('WARDEN screen observation timed out; action was not run')); }, 10_000);
      pending.set(id, { resolve: resolveScreen, reject, timer, screen: true });
      try { childWrite(JSON.stringify({ jsonrpc: '2.0', id, method: 'tools/call', params: { name: opts.screenRead, arguments: opts.screenReadInput ?? {} } })); }
      catch (err) { clearTimeout(timer); pending.delete(id); reject(err); }
    });
    const prepareAtomic = (tool: string, args: Record<string, unknown>): Promise<{ result: any; bytes: number }> => new Promise((resolveScreen, reject) => {
      const id = prefix + seq++;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('Atomic preparation timed out; action was not run')); }, 10_000);
      pending.set(id, { resolve: resolveScreen, reject, timer, screen: true });
      try { childWrite(JSON.stringify({ jsonrpc: '2.0', id, method: ATOMIC_SCREEN_PREPARE, params: { protocol: ATOMIC_SCREEN_PROTOCOL,
        observation: { name: opts.screenRead, arguments: opts.screenReadInput ?? {} }, action: { name: tool, arguments: args } } })); }
      catch (err) { clearTimeout(timer); pending.delete(id); reject(err); }
    });
    const listAll = (): Promise<ToolDef[]> => listAllTools(requestPage);
    const check = (): Promise<ToolDef[]> => {
      if (refresh) return refresh;
      const epoch = generation;
      const work = (async () => {
        const tools = await listAll();
        const verdict = await vetAndPin(opts.stateDir, server, tools, opts.policy, store, warden, feed, opts.auditOnly, () => epoch === generation && !closing, record, serverInfo);
        if (!opts.auditOnly && epoch !== generation) throw new WardenBlock('tools changed, blocked by WARDEN during verification');
        if (!opts.auditOnly && !verdict.allow) throw new WardenBlock(reason(verdict));
        if (closing) throw new Error('MCP connection closing');
        blockReason = ''; quarantined = false;
        return opts.auditOnly ? tools : tools.filter(t => verdict.allowedTools.includes(t.name));
      })();
      refresh = work;
      void work.then(() => { if (refresh === work) refresh = undefined; }, e => {
        if (refresh === work) refresh = undefined;
        quarantined = true; quarantineKind = e instanceof WardenBlock ? 'blocked' : 'error';
        blockReason = e instanceof Error ? e.message : String(e); log.warn(blockReason);
      });
      return work;
    };
    // Batches (allowed by protocol 2025-03-26, removed in 2025-06-18) are refused per request,
    // as an array of errors, rather than ending the session: each element would need its own
    // tools/list and tools/call checks, and splitting them would change the reply shape.
    const refuseBatch = (body: string): boolean => {
      let raw: unknown;
      try { raw = JSON.parse(body); } catch { return false; }
      if (!Array.isArray(raw)) return false;
      if (raw.length === 0) { send({ jsonrpc: '2.0', id: null, error: { code: -32600, message: 'Invalid Request: empty batch' } }); return true; }
      const replies = raw.filter((m): m is Message => !!m && typeof m === 'object' && !Array.isArray(m) && m.method !== undefined && m.id !== undefined)
        .map(m => ({ jsonrpc: '2.0', id: typeof m.id === 'string' || typeof m.id === 'number' ? m.id : null,
          error: { code: -32600, message: 'warden wrap does not accept JSON-RPC batches; send each request on its own' } }));
      if (replies.length) send(replies);
      return true;
    };
    const fromClient = async (body: string) => {
      if (refuseBatch(body)) return;
      const msg = parse(body);
      if (typeof msg.id === 'string' && msg.id.startsWith(prefix)) {
        // The client's answer to a question this proxy asked. A late one (after a timeout) is dropped.
        if (msg.method === undefined) {
          const r = msg.result as { action?: unknown; content?: { run?: unknown } } | undefined;
          answer(msg.id, msg.error !== undefined ? 'error' : r?.action === 'accept' && r.content?.run === true ? 'approved' : r?.action === 'cancel' ? 'cancelled' : 'declined');
          return;
        }
        fail(msg, 'Reserved proxy request ID'); return;
      }
      if (blockedLaunch) {
        fail(msg, blockReason, -32000);
        if (msg.method === 'initialize') finish(3);
        return;
      }
      if (closing) return;
      // Internal capabilities/tickets belong to this proxy, never to client/model requests.
      if (msg.method?.startsWith('warden/screen/')) { fail(msg, 'Reserved WARDEN atomic screen method'); return; }
      if (msg.method === 'initialize' && msg.params?.capabilities && typeof msg.params.capabilities === 'object') clientCapabilities = msg.params.capabilities as Record<string, unknown>;
      if (msg.method === 'notifications/cancelled') {
        // A call still being checked, or waiting for a person, was never sent on: stop it here.
        const requestId = msg.params?.requestId;
        const wait = typeof requestId === 'string' || typeof requestId === 'number' ? waiting.get(requestId) : undefined;
        if (wait) {
          wait.cancelled = true;
          if (wait.question && questions.has(wait.question)) { answer(wait.question, 'cancelled'); withdraw(wait.question, 'the client cancelled the call'); }
          return;
        }
      }
      if (msg.method === 'tools/list' || msg.method === 'tools/call') {
        if (msg.id === undefined) return; // These are requests, never notifications.
        if (activeChecks >= 256) { fail(msg, 'Too many pending MCP requests'); return; }
        activeChecks++;
        try {
          if (msg.method === 'tools/list') {
            const tools = await check();
            if (!opts.auditOnly && quarantined) throw new Error(blockReason || 'tools changed, blocked by WARDEN');
            visible = tools;
            send({ jsonrpc: '2.0', id: msg.id, result: { tools } });
          } else {
            const name = msg.params?.name;
            const seen = visible.find(t => t.name === name);
            // A failed check is retried here; a refusal or a change waits for the client to re-list.
            if (!opts.auditOnly && ((quarantined && quarantineKind !== 'error') || !seen)) throw new Error(blockReason || 'tool blocked by WARDEN');
            if (tracked.size >= 256 || tracked.has(msg.id) || waiting.has(msg.id)) throw new Error('Too many or duplicate pending MCP requests');
            const wait: { cancelled: boolean; question?: string } = { cancelled: false };
            waiting.set(msg.id, wait);
            let releaseScreen: ((abandon?: boolean) => void) | undefined;
            let screenChecking = false, humanApproved = false;
            let atomic: AtomicScreenPrepared | undefined;
            try {
              const epoch = generation;
              const current = await check();
              const def = current.find(t => t.name === name);
              if (!opts.auditOnly && (quarantined || epoch !== generation || !def || !seen || pinToolsHash([def]) !== pinToolsHash([seen]))) throw new Error('tool blocked by WARDEN: definition changed since exposure');
              if (tracked.size >= 256 || tracked.has(msg.id)) throw new Error('Too many or duplicate pending MCP requests');
              const tool = String(name);
              if (msg.params?.arguments !== undefined && (!msg.params.arguments || typeof msg.params.arguments !== 'object' || Array.isArray(msg.params.arguments))) throw new Error('Invalid MCP tool arguments: expected a JSON object');
              const args = msg.params?.arguments && typeof msg.params.arguments === 'object' && !Array.isArray(msg.params.arguments) ? msg.params.arguments as Record<string, unknown> : {};
              const isGui = !!opts.flow && !!screenCall(flowTool(tool), args, { v: 1, untrusted: [], private: [], notified: false, full: false });
              if (isGui && opts.screenAtomic && (!['ask', 'deny'].includes(loadPolicy().mode) || Object.keys(msg).some(k => !['jsonrpc', 'id', 'method', 'params'].includes(k)) || Object.keys(msg.params ?? {}).some(k => !['name', 'arguments'].includes(k)))) throw new Error('Atomic screen requires enforcing flow policy and exact call schema; action was not run');
              if (isGui && opts.screenAtomic && displaySafe(JSON.stringify(args), 100_000).length > 1500) throw new Error('Atomic action arguments exceed the complete approval preview limit; action was not run');
              if (isGui && !opts.auditOnly && (opts.screenRead || ['ask', 'deny'].includes(loadPolicy().mode))) releaseScreen = screenLease(flowSession);
              const observeTarget = async (): Promise<string> => {
                screenChecking = true;
                const observedDef = current.find(t => t.name === opts.screenRead), exposedDef = visible.find(t => t.name === opts.screenRead);
                if (!observedDef || !exposedDef || isSensitiveTool(observedDef.name, opts.policy) || pinToolsHash([observedDef]) !== pinToolsHash([exposedDef])) throw new Error('WARDEN: configured observation tool is not independently available for read; action was not run');
                const preparing = opts.screenAtomic && !atomic;
                const r = preparing ? await prepareAtomic(tool, args) : await requestScreen();
                if (preparing) atomic = atomicScreenPrepared(r.result);
                const observation = preparing ? atomic!.observation : r.result;
                if (wait.cancelled) throw new CallCancelled();
                if (closing || quarantined || epoch !== generation || !observation || observation.isError) throw new Error('WARDEN: screen observation failed or was cancelled; action was not run');
                flowPost({ session_id: flowSession, cwd: process.cwd(), tool_name: flowTool(opts.screenRead!), tool_input: opts.screenReadInput ?? {}, tool_response: observation });
                const stamp = screenResponseStamp(flowTool(tool), args, flowTool(opts.screenRead!), opts.screenReadInput ?? {}, observation);
                if (!stamp) throw new Error('WARDEN: fresh screen cannot establish an unambiguous target, role, ID, bounds and context; action was not run');
                if (preparing && stamp !== atomic!.stamp) throw new Error('Atomic server target binding differs from observation; action was not run');
                return stamp;
              };
              const atomicTarget = isGui && opts.screenAtomic ? await observeTarget() : undefined;
              // A call that needs a person's yes: a tool the operator marked sensitive, or a send the flow guard asks about.
              const reasons: string[] = [];
              if (isSensitiveTool(tool, opts.policy)) reasons.push(`${displaySafe(tool, 200)} matches policy.sensitiveToolPatterns: every call to it needs a person's approval.`);
              const flowPolicy = opts.flow ? loadPolicy() : undefined;
              const annotation = flowPolicy && opts.flow ? annotationReview(server, current, tool, opts.flow, flowPolicy, opts.policy.capabilityBindings) : undefined;
              const firstAnnotationUse = annotation && !reviewedAnnotations.has(annotation.key) ? annotation : undefined;
              const annotationEnforced = firstAnnotationUse && !opts.auditOnly && flowPolicy?.mode !== 'audit';
              if (firstAnnotationUse && !annotationEnforced) log.warn(`would ask before first use of ${displaySafe(tool, 200)}: unverified MCP annotations`);
              if (annotationEnforced) {
                if (flowPolicy?.mode === 'deny') throw new Error('tool blocked by WARDEN: unreviewed MCP annotations in deny mode; the tool was not run');
                reasons.push(firstAnnotationUse.reason);
              }
              let flowAsked = false;
              if (opts.flow) {
                const d = flowPre({ session_id: flowSession, cwd: process.cwd(), tool_name: flowTool(tool), tool_input: args, public_request_eligible: Object.keys(msg.params ?? {}).every(k => ['name', 'arguments'].includes(k)) && Object.keys(msg).every(k => ['jsonrpc', 'id', 'method', 'params'].includes(k)) }, process.env, opts.auditOnly ? 'audit' : canAsk() ? 'elicit' : 'refuse');
                if (d && !opts.auditOnly) {
                  if (d.permissionDecision === 'deny' || !canAsk()) throw new Error(`${d.permissionDecisionReason}${d.permissionDecision === 'ask' ? ` Refused: wrap cannot ask you${cannotAsk()}; name the destination in the flow policy (allowedDestinations) or make the call yourself.` : ''}`);
                  reasons.push(d.permissionDecisionReason); flowAsked = true;
                }
                if (d && opts.auditOnly) log.warn(`flow guard would ${d.permissionDecision} ${flowTool(tool)}`);
              }
              if (reasons.length && opts.auditOnly) log.warn(`would ask a person before ${displaySafe(tool, 200)} runs (sensitive tool)`);
              else if (reasons.length) {
                if (!canAsk()) throw new Error(`tool blocked by WARDEN: ${displaySafe(tool, 200)} needs a person's approval (${annotationEnforced ? 'unreviewed MCP annotations' : 'policy.sensitiveToolPatterns'}), and wrap cannot ask you${cannotAsk()}; it was not run`);
                const targetBefore = atomicTarget ?? (isGui && opts.screenRead ? await observeTarget() : undefined);
                let approvedBasis: ReturnType<typeof flowPre>;
                if (targetBefore) {
                  const updated = flowPre({ session_id: flowSession, cwd: process.cwd(), tool_name: flowTool(tool), tool_input: args, public_request_eligible: false }, process.env, 'elicit');
                  if (updated?.permissionDecision === 'deny') throw new Error(updated.permissionDecisionReason);
                  approvedBasis = updated;
                  if (flowAsked) reasons.pop();
                  if (updated) { reasons.push(updated.permissionDecisionReason); flowAsked = true; }
                  reasons.push(opts.screenAtomic ? 'The trusted server must atomically compare this exact target and revision and commit this one action. Stale/replayed approvals are refused; there is no raw-call fallback.' : 'WARDEN will read the screen again after approval and cancel if the target or context differs. Matching metadata does not attest the action’s effect.');
                }
                const outcome = await askPerson(msg.id, tool, args, reasons);
                if (flowAsked) flowApproval({ session_id: flowSession, tool_name: flowTool(tool) }, outcome);
                if (wait.cancelled) throw new CallCancelled();
                if (outcome !== 'approved') throw new Error(`tool call refused by WARDEN: ${outcome === 'timeout' ? 'no answer to the approval request within 5 minutes' : outcome === 'closed' ? 'the connection closed before an answer' : outcome === 'error' ? 'the client could not show the approval request' : 'it was not approved'}; ${displaySafe(tool, 200)} was not run`);
                humanApproved = true;
                // The person approved the definition the client was shown; it must still be the one that runs.
                if (quarantined || epoch !== generation) throw new Error('tool blocked by WARDEN: definitions changed while waiting for approval; list tools again');
                if (targetBefore || annotationEnforced) {
                  const reviewed = await check();
                  if (quarantined || epoch !== generation || pinToolsHash(reviewed) !== pinToolsHash(current)) throw new Error('WARDEN: definitions changed since the approval prompt; action was not run');
                }
                if (targetBefore && await observeTarget() !== targetBefore) throw new Error('WARDEN: screen target or context changed since approval was requested; action was not run');
                if (targetBefore) {
                  const updated = flowPre({ session_id: flowSession, cwd: process.cwd(), tool_name: flowTool(tool), tool_input: args, public_request_eligible: false }, process.env, 'elicit');
                  if (updated?.permissionDecision === 'deny') throw new Error(updated.permissionDecisionReason);
                  if (JSON.stringify(updated) !== JSON.stringify(approvedBasis)) throw new Error('WARDEN: the risk context changed while approval was pending; action was not run');
                  flowScreenValidation({ session_id: flowSession, tool_name: flowTool(tool) }, 'unchanged');
                }
              }
              if (wait.cancelled) throw new CallCancelled();
              if (quarantined || epoch !== generation) throw new Error('WARDEN: definitions changed before execution');
              if (atomic && atomic.expiresAt <= Date.now()) throw new Error('Atomic approval expired; action was not run');
              if (annotationEnforced && humanApproved) reviewedAnnotations.add(firstAnnotationUse.key);
              tracked.set(msg.id, { kind: 'call', generation, tool, args, screenRelease: releaseScreen, atomic });
              releaseScreen = undefined;
              // Forward the inspected object: ignored duplicate JSON fields must not carry hidden bytes.
              const forward = atomic ? { jsonrpc: '2.0', id: msg.id, method: ATOMIC_SCREEN_COMMIT, params: { protocol: ATOMIC_SCREEN_PROTOCOL, ticket: atomic.ticket,
                expected: { revision: atomic.revision, stamp: atomic.stamp }, action: { name: tool, arguments: args } } } : msg;
              atomic = undefined; // Now tracked; cancellation/crash may mean the effect happened.
              childWrite(opts.flow && !opts.auditOnly ? JSON.stringify(forward) : body);
            } catch (err) {
              if (screenChecking) flowScreenValidation({ session_id: flowSession, tool_name: flowTool(String(name)) }, tracked.has(msg.id) ? 'execution_uncertain' : humanApproved ? 'refused_after_approval' : 'refused_without_approval');
              throw err;
            } finally {
              if (atomic && !closing) { try { childWrite(JSON.stringify({ jsonrpc: '2.0', method: ATOMIC_SCREEN_CANCEL, params: { protocol: ATOMIC_SCREEN_PROTOCOL, ticket: atomic.ticket } })); } catch { /* no effect; ticket expires */ } }
              releaseScreen?.(); waiting.delete(msg.id);
            }
          }
        } catch (e) { if (!(e instanceof CallCancelled)) fail(msg, e instanceof Error ? e.message : String(e)); }
        finally { activeChecks--; }
        return;
      }
      if (msg.method !== undefined && msg.id !== undefined) {
        if (tracked.size >= 256 || tracked.has(msg.id)) { fail(msg, 'Too many or duplicate pending MCP requests'); return; }
        tracked.set(msg.id, { kind: msg.method === 'initialize' ? 'initialize' : 'other', generation });
      }
      childWrite(body);
    };
    const fromChild = async (body: string) => {
      const msg = parse(body);
      if (msg.method === undefined && typeof msg.id === 'string' && msg.id.startsWith(prefix)) {
        const p = pending.get(msg.id);
        if (!p) return; // Timed-out internal response must never leak to the client.
        clearTimeout(p.timer); pending.delete(msg.id);
        if (msg.error) p.reject(new Error(p.screen ? 'WARDEN: screen observation failed; action was not run' : 'MCP tools/list failed: ' + JSON.stringify(msg.error)));
        else p.resolve({ result: msg.result, bytes: Buffer.byteLength(body) });
        return;
      }
      if (msg.method === 'notifications/tools/list_changed') {
        generation++; quarantined = true; quarantineKind = 'changed'; blockReason = 'tools changed, blocked by WARDEN';
        const epoch = generation;
        // Do not reuse a check that started before the notification.
        void (async () => {
          await refresh?.catch(() => {});
          if (epoch !== generation || closing) return;
          await check();
          if (epoch === generation && !closing && (!quarantined || opts.auditOnly)) clientWrite(body);
        })().catch(e => log.warn(e instanceof Error ? e.message : String(e)));
        return;
      }
      if (msg.method === undefined && msg.id !== undefined) {
        const request = tracked.get(msg.id);
        if (!request) { log.warn(`dropped a child response to request ${displaySafe(JSON.stringify(msg.id), 80)}, which the client did not send to it or already received`); return; }
        {
          tracked.delete(msg.id);
          if (request.atomic) {
            try {
              if (msg.error !== undefined) throw new Error('Atomic commit returned an error');
              const receipt = atomicScreenReceipt(msg.result, request.atomic);
              if (receipt.status === 'refused') {
                request.screenRelease?.();
                flowScreenValidation({ session_id: flowSession, tool_name: flowTool(request.tool ?? '') }, 'atomic_refused');
                fail(msg, 'WARDEN: atomic server refused the stale, expired or mismatched approval; action was not run'); return;
              }
              msg.result = receipt.result;
              body = JSON.stringify(msg);
              flowScreenValidation({ session_id: flowSession, tool_name: flowTool(request.tool ?? '') }, 'atomic_committed');
            } catch {
              request.screenRelease?.(true);
              flowScreenValidation({ session_id: flowSession, tool_name: flowTool(request.tool ?? '') }, 'execution_uncertain');
              fail(msg, 'WARDEN: atomic execution result is uncertain; reconcile before retrying'); return;
            }
          }
          if (opts.flow && request.kind === 'call' && (msg.result !== undefined || msg.error !== undefined)) {
            // Record what the result brought into the session (outside text, private data) before anything else.
            try { flowPost({ session_id: flowSession, cwd: process.cwd(), tool_name: flowTool(request.tool ?? ''), tool_input: request.args ?? {}, tool_response: msg.error !== undefined ? { error: msg.error } : msg.result, ...(msg.error !== undefined ? { tool_error: msg.error } : {}) }); }
            catch (e) {
              log.warn(`flow guard could not record a result: ${e instanceof Error ? e.message : String(e)}`);
              if (!opts.auditOnly) { request.screenRelease?.(true); fail(msg, 'WARDEN flow guard could not record this response; withheld to avoid untracked outside text'); return; }
            }
          }
          request.screenRelease?.();
          if (request.kind === 'call' && !opts.auditOnly && (quarantined || request.generation !== generation)) {
            fail(msg, 'tools changed, blocked by WARDEN; result withheld, execution may already have occurred'); return;
          }
          if (request.kind === 'call' && opts.results !== 'off' && msg.result && typeof msg.result === 'object') {
            // The result is new text every call, from wherever the tool reads: screen it as it passes.
            const tool = request.tool ?? '';
            const screen = await screenResult(server, tool, msg.result, opts.policy);
            if (screen.flagged) {
              if (screen.verdict) record(screen.verdict);
              if (!opts.auditOnly) {
                if (opts.results === 'block') {
                  fail(msg, `tool result withheld by WARDEN: ${screen.complete ? 'it reads as instructions to the model' : 'inspection is incomplete'} (${screen.codes.join(', ')}); the tool already ran`); return;
                }
                send({ ...msg, result: annotateResult(msg.result, tool, screen.codes) }); return;
              }
            }
          }
          if (request.kind === 'initialize' && msg.result && typeof msg.result === 'object') {
            serverInfo = observedServerInfo(msg.result.serverInfo);
            msg.result.capabilities = { ...msg.result.capabilities, tools: { ...msg.result.capabilities?.tools, listChanged: true } };
            if (typeof msg.result.instructions === 'string') {
              const scan = new Warden({ policy: opts.policy, gates: [new StaticScanGate()] });
              const verdict = await scan.vet(server, [{ name: 'initialize.instructions', description: msg.result.instructions, inputSchema: { type: 'object' } }]);
              record(verdict);
              if ((!verdict.allow || opts.policy.requireApproval) && !opts.auditOnly) delete msg.result.instructions;
            } else if (msg.result.instructions !== undefined && !opts.auditOnly) delete msg.result.instructions;
            send(msg); return;
          }
        }
      }
      clientWrite(body);
    };
    process.stdout.on('error', fatal);
    process.once('SIGTERM', signalStop); process.once('SIGINT', signalStop);
    if (!blockedLaunch) {
      child = spawn(server.command!, server.args!, { stdio: ['pipe', 'pipe', 'pipe'], env: process.env });
      child.on('error', e => { log.error(e.message); finish(1); });
      child.on('close', (code, signal) => finish(code ?? (signal ? 128 + (constants.signals[signal] ?? 0) : 1)));
      child.stdin.on('error', fatal);
      // Bound and sanitize each chunk; a child cannot accumulate an unterminated stderr line.
      child.stderr.on('data', chunk => {
        for (const line of String(chunk).split('\n').filter(Boolean)) process.stderr.write(`warden: ${opts.auditOnly ? 'AUDIT-ONLY ' : ''}[child ${displaySafe(server.id)}] ${displaySafe(line, 8192)}\n`);
      });
      readFrames(child.stdout, new WrapFrames('ndjson'), body => { void fromChild(body).catch(fatal); }, fatal, () => {});
    }
    readFrames(process.stdin, frames, body => { void fromClient(body).catch(fatal); }, fatal, stop);
  });
}
