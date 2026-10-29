// GENERATED from src/flow-guard-pre.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard, PreToolUse: whether a call asks first, is denied or passes. */
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { absPath, flowPaths, isSecretPath, sessionKey, stateDir } from './flow-guard-paths.mjs';
import { globMatch, loadPolicy, publicRequestDigest, taskDelegation } from './flow-guard-policy.mjs';
import { classifyCall } from './flow-guard-classify.mjs';
import { guiOperation, screenCall } from './flow-guard-screen.mjs';
import { DEST_ARG_NAMES, allowedDestination, destinations, hasDestinationArgument, keepsDestination, namedByUser } from './flow-guard-destinations.mjs';
import { piiTokens, secretPattern } from './flow-guard-fingerprints.mjs';
import { candidates } from './flow-guard-decode.mjs';
import { checkFragments } from './flow-guard-fragments.mjs';
import { checkLeak, checkStream, readFp, readStores } from './flow-guard-leak.mjs';
import { log, readFlowState, safeToolName, updateFlowState } from './flow-guard-state.mjs';
const MAX_TAIL_KEYS = 32;
/** Tainted by MCP definitions: a server the session-start scan blocked or could not check still put its text in the context. */
function definitionTaint(dir, sessionId) {
    try {
        const v = JSON.parse(readFileSync(join(dir, 'claude-code', 'sessions', `${sessionKey(sessionId)}.json`), 'utf8'));
        const bad = (v.servers || []).find(s => s.allow === false || s.status === 'error' || (s.blockedTools && s.blockedTools.length));
        return bad ? `MCP server "${safeToolName(String(bad.key))}" definitions` : undefined;
    }
    catch {
        return undefined;
    }
}
function sourcesText(s, extra) {
    // Tool identity establishes which result was read, not which result supplied a destination.
    // Do not echo source URLs (which can carry credentials) or arbitrary result text into the dialog.
    const list = [...(extra ? [extra] : []), ...s.untrusted.map(u => safeToolName(u.tool))];
    const uniq = [...new Set(list)].slice(-3);
    return uniq.join(', ') || 'outside text';
}
/** A short destination preview, never the outgoing message, shell program or credential value. */
function targetSummary(toolName, input, policy, sensitivePayload) {
    const configured = Object.entries(policy.destinationArgs).find(([glob]) => globMatch(glob, toolName))?.[1];
    const names = configured ? new Set(configured.map(n => n.toLowerCase())) : DEST_ARG_NAMES;
    const targets = [];
    let omitted = false;
    const add = (field, value, depth = 0) => {
        if (targets.length >= 4) {
            omitted = true;
            return;
        }
        if (depth > 4) {
            targets.push(`${field}=[nested target omitted]`);
            return;
        }
        if (Array.isArray(value)) {
            for (const v of value) {
                add(field, v, depth + 1);
                if (omitted)
                    break;
            }
            return;
        }
        if (value && typeof value === 'object') {
            for (const v of Object.values(value)) {
                add(field, v, depth + 1);
                if (omitted)
                    break;
            }
            return;
        }
        if (typeof value !== 'string' && typeof value !== 'number')
            return;
        const raw = String(value);
        // The main check already loaded the fingerprint stores. Do not reload them per recipient.
        if (sensitivePayload || raw.length > 200 || secretPattern(candidates([raw])) || piiTokens(raw).length) {
            targets.push(`${field}=[redacted]`);
            return;
        }
        let preview = raw;
        if (/^https?:\/\//i.test(raw)) {
            try {
                preview = new URL(raw).origin + ' (URL path/query omitted)';
            }
            catch {
                preview = '[unrecognized URL]';
            }
        }
        else if (!/^[#@A-Za-z0-9_.+:/-]{1,100}$/.test(raw)) {
            // Attacker-authored prose, control characters, bidi and markup are not dialog instructions.
            preview = '[target text omitted]';
        }
        targets.push(`${field}=${JSON.stringify(preview)}`);
    };
    for (const [key, value] of Object.entries(input)) {
        if (names.has(key.toLowerCase()))
            add(safeToolName(key), value);
        if (omitted)
            break;
    }
    return targets.length ? targets.join(', ') + (omitted ? '; additional targets omitted — review full call' : '') : 'not identified in destination arguments; review full call';
}
function credentialSession(state, stores) {
    return !!(state.credentialRead || state.private.some(s => s.secret) || state.fragments?.index.length || stores.secret.size || stores.tok.size);
}
function reservePublicRequest(paths, tool, input, checked, policy, env) {
    const digest = publicRequestDigest(tool, input);
    if (!digest || policy.mode !== 'ask' || !policy.credentialEgress?.allow.some(r => r.tool === tool && r.requestSha256 === digest))
        return;
    let grant;
    mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
    updateFlowState(paths.state, current => {
        const fresh = loadPolicy(env);
        if (fresh.mode !== policy.mode || !fresh.credentialEgress?.allow.some(r => r.tool === tool && r.requestSha256 === digest))
            return;
        if (current.full || current.credentialGrants?.includes(digest) || (current.credentialGrants?.length ?? 0) >= 32)
            return;
        const stores = readStores(paths), leak = checkLeak(paths, checked, current.intent, stores);
        const fragments = checkFragments(checked, current, stores.tok.size > 0, false);
        const stream = checkStream(checked, current.tails ?? {}, stores).leak;
        if (stream.secret || stream.private || stream.pii || leak.secret || leak.private || leak.pii || leak.incomplete || fragments.secret || fragments.review || fragments.unavailable)
            return;
        current.credentialGrants = [...(current.credentialGrants ?? []), digest];
        current.credentialRead = true;
        grant = digest;
    });
    return grant;
}
export function flowPre(input, env = process.env, presentation = 'hook') {
    const policy = loadPolicy(env);
    if (policy.mode === 'off')
        return undefined;
    const toolName = typeof input.tool_name === 'string' ? input.tool_name : '';
    const sessionId = typeof input.session_id === 'string' ? input.session_id : '';
    const cwd = typeof input.cwd === 'string' && input.cwd ? input.cwd : process.cwd();
    const toolInput = input.tool_input && typeof input.tool_input === 'object' && !Array.isArray(input.tool_input) ? input.tool_input : {};
    if (!toolName || !sessionId)
        return undefined;
    if (input.tool_input !== undefined && (!input.tool_input || typeof input.tool_input !== 'object' || Array.isArray(input.tool_input)))
        return { permissionDecision: 'deny', permissionDecisionReason: 'WARDEN flow guard: tool arguments must be a JSON object; malformed input cannot receive a public-request grant.' };
    const dir = stateDir(env);
    const paths = flowPaths(dir, sessionId);
    const publicEligible = input.public_request_eligible !== false && (input.tool_input === undefined || !!input.tool_input && typeof input.tool_input === 'object' && !Array.isArray(input.tool_input));
    if (publicEligible && presentation !== 'audit' && taskDelegation(toolName, toolInput, policy, env)) {
        log(paths, { event: 'pre', tool: safeToolName(toolName), decision: 'allow', reason: 'task_adapter_delegated',
            disposition: 'policy_allowed', approvalOutcome: 'unknown', mode: policy.mode });
        return undefined;
    }
    const c = classifyCall(toolName, toolInput, cwd, policy, env);
    const state = readFlowState(paths.state);
    // A click is what it lands on. This only adds caution, so it applies to operator-labelled tools too: a glob that
    // labels a screen server's screenshots must not switch off the check on its clicks.
    const screen = screenCall(toolName, toolInput, state);
    if (screen?.verb)
        c.labels.add('outbound');
    if (screen?.destroy)
        c.labels.add('destructive');
    const defTaint = definitionTaint(dir, sessionId);
    const tainted = state.untrusted.length > 0 || !!defTaint;
    let decision;
    let reason;
    let sensitivePayload = false;
    let publicGrant;
    if (c.protectedTouch) {
        reason = 'protected_settings';
        sensitivePayload = true;
        decision = { permissionDecision: tainted ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: this call would change WARDEN's policy or Claude Code's hook/MCP settings${tainted ? ` after the session read outside text (${sourcesText(state, defTaint)})` : ''}.` };
    }
    else if (tainted && (c.labels.has('outbound') || toolName.startsWith('mcp__') || ['WebFetch', 'WebSearch'].includes(toolName))) {
        const stores = readStores(paths);
        const leak = checkLeak(paths, toolInput, state.intent, stores);
        const stream = checkStream(toolInput, state.tails ?? {}, stores);
        let credential = credentialSession(state, stores);
        leak.secret ||= stream.leak.secret;
        leak.private ||= stream.leak.private;
        leak.pii ||= stream.leak.pii;
        // Conservative observations include refused calls, and survive prompts/server changes. Re-evaluate under
        // the shared lock so simultaneous proxies cannot both send the two halves of the same credential.
        let fragments = {};
        if (policy.mode === 'audit' || presentation === 'audit') {
            fragments = checkFragments(toolInput, state, stores.tok.size > 0, false);
        }
        else {
            mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
            updateFlowState(paths.state, current => {
                const currentStores = readStores(paths);
                credential ||= credentialSession(current, currentStores);
                if (credential)
                    current.credentialRead = true;
                const currentLeak = checkLeak(paths, toolInput, current.intent, currentStores);
                const currentStream = checkStream(toolInput, current.tails ?? {}, currentStores);
                leak.secret ||= currentLeak.secret || currentStream.leak.secret;
                leak.private ||= currentLeak.private || currentStream.leak.private;
                leak.pii ||= currentLeak.pii || currentStream.leak.pii;
                leak.incomplete ||= currentLeak.incomplete;
                fragments = checkFragments(toolInput, current, currentStores.tok.size > 0, true);
                current.tails = Object.fromEntries(Object.entries({ ...(current.tails ?? {}), ...currentStream.next }).slice(-MAX_TAIL_KEYS));
            });
        }
        leak.secret ||= fragments.secret;
        sensitivePayload = !!(leak.secret || leak.private || leak.pii || leak.incomplete || credential || fragments.review || fragments.unavailable);
        const dests = destinations(toolName, toolInput, policy, c.hosts);
        const targetKnown = hasDestinationArgument(toolName, toolInput, policy);
        const allowedHosts = targetKnown && dests.length > 0 && dests.every(d => allowedDestination(d, policy.allowedDestinations));
        const contacts = state.resolvedVersion === 2 ? state.resolved : undefined;
        const userNamed = (targetKnown && namedByUser(dests, state.intent, state.intentRaw, contacts)) || (dests.length === 0 && keepsDestination(toolName, toolInput, policy));
        if (c.opaqueShell && c.secret)
            leak.secret = 'credential file referenced by shell code';
        if (!leak.secret && fragments.review) {
            reason = 'secret_fragment';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: an argument matches a short fragment of a credential read this session. A short match can be coincidental, so review it before transmission. Named or allowed destinations and earlier approvals do not exempt this call.' };
        }
        else if (!leak.secret && screen?.paste) {
            reason = 'paste_after_secret';
            sensitivePayload = true;
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: this call pastes the clipboard after the session read a credential (${screen.paste.src.slice(0, 80)}) and outside text (${sourcesText(state, defTaint)}). What a paste carries is not in its arguments, so the guard cannot check it. Allow it only if you know what the clipboard holds.` };
        }
        else if (leak.secret) {
            reason = 'secret';
            decision = { permissionDecision: 'deny', permissionDecisionReason: `WARDEN flow guard: this call carries a secret (${leak.secret}) after the session read outside text (${sourcesText(state, defTaint)}). Denied.` };
        }
        else if (leak.incomplete) {
            reason = 'payload_incomplete';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: the bounded payload decoder could not finish checking this request. Review it before execution; no automatic public-request grant applies.' };
        }
        else if (fragments.unavailable) {
            reason = 'secret_tracking';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: short-secret tracking is incomplete or at capacity. This call after outside text requires review even for a named or allowed destination. Start a new session and reread private sources to restore tracking.' };
        }
        else if (c.opaqueShell) {
            reason = 'opaque_shell';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: after outside text, shell code outside the literal read-only subset requires approval. Named or allowed hosts do not authorize shell programs, hooks, redirections or file uploads.' };
        }
        else if (leak.pii) {
            reason = 'personal_data';
            // Card, passport, account or phone numbers read this session: even to a destination the user named,
            // unless the user typed the value. Which of the user's numbers to send is what an injection would pick.
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: an argument matches a personal-data fingerprint recorded during this session, after outside text (${sourcesText(state, defTaint)}). The matching source was not retained. Check what is being sent.` };
        }
        else if (leak.private && !userNamed) {
            reason = 'private_text';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: an argument matches a private-text fingerprint recorded during this session, after outside text (${sourcesText(state, defTaint)}), and the destination is not confirmed as user-named. The matching source was not retained. Check what is being sent.` };
        }
        else if (credential && !screen?.guarded) {
            if (publicEligible && presentation !== 'audit' && !c.labels.has('destructive') && !guiOperation(toolName, toolInput))
                publicGrant = reservePublicRequest(paths, toolName, toolInput, toolInput, policy, env);
            if (!publicGrant) {
                reason = 'credential_egress';
                decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: this session holds credentials and outside text. Review this outbound request before execution, regardless of fragment length, encoding or destination. This is a credential boundary, not a claim that its contents are a detected secret.' };
            }
        }
        else if (screen?.guarded) {
            reason = 'screen_action';
            const actions = { pointer: 'a pointer action', paste: 'a clipboard paste', enter: 'Enter/Return', text: 'text input', keyboard: 'a keyboard action', control: 'an unresolved GUI control action' };
            const policyNote = policy.gui?.invalid ? ' Invalid GUI policy: strict behavior is active.' : policy.gui?.mode === 'policy' ? ' Legacy GUI allow rules cannot authorize actions from untrusted screen metadata. Use the built-in task adapter for constrained operations.' : '';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: ${actions[screen.guarded]} follows outside text (${sourcesText(state, defTaint)}). Screen labels, coordinates, images and key arguments do not establish what this action will send or change. Check the actual window, target and effect before allowing it. A named or allowed destination does not authorize GUI actions.${policyNote}` };
        }
        else if (c.labels.has('outbound') && !allowedHosts && !userNamed) {
            reason = 'unnamed_destination';
            // Not only leaks: an outbound call acts with the user's authority (a message, a payment, an invite),
            // which an injection wants as much as their data. So it does not wait for a private read.
            const what = state.private.length > 0 || state.full ? 'and private data; this call can send data out or act for you' : '; this call can act for you or send data out';
            decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: the session read outside text (${sourcesText(state, defTaint)}) ${what}. A destination is missing or not confirmed by your recorded messages or destination policy; addresses and links in content also count. Its origin is not tracked. Allow only if this action and destination match your request.`.replace(') ;', ');') };
        }
    }
    // A file the agent writes inside the project can leave later without another call: CI publishes docs/, a commit
    // is pushed by a person. After outside text, a key read this session written into an ordinary project file asks;
    // credential files (.env, .npmrc …) remain exempt. Ordinary writes need review after a credential read,
    if (!decision && tainted && ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'].includes(toolName)) {
        const target = typeof toolInput.file_path === 'string' ? toolInput.file_path : typeof toolInput.notebook_path === 'string' ? toolInput.notebook_path : '';
        if (!target || !isSecretPath(absPath(target, cwd))) {
            const written = { content: toolInput.content, new_string: toolInput.new_string, new_source: toolInput.new_source,
                edits: Array.isArray(toolInput.edits) ? toolInput.edits.map(e => (e && typeof e === 'object' ? e.new_string : undefined)) : undefined };
            const leak = checkLeak(paths, written);
            let fragments = {};
            if (policy.mode === 'audit' || presentation === 'audit')
                fragments = checkFragments(written, state, readFp(paths.tok).size > 0, false);
            else {
                mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
                updateFlowState(paths.state, current => { fragments = checkFragments(written, current, readFp(paths.tok).size > 0, true); });
            }
            leak.secret ||= fragments.secret;
            const credential = credentialSession(readFlowState(paths.state), readStores(paths));
            if (leak.secret || fragments.review || fragments.unavailable || leak.incomplete) {
                reason = 'secret_to_file';
                sensitivePayload = true;
                decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: leak.secret ? `WARDEN flow guard: this write puts a secret (${leak.secret}) into a project file after the session read outside text (${sourcesText(state, defTaint)}). Files in the project can be committed or published later. Allow it only if you asked for this key to go into this file.` : fragments.review ? 'WARDEN flow guard: this project-file write matches a short credential fragment. Review it before writing; project files can be published later.' : 'WARDEN flow guard: short-secret tracking is incomplete or at capacity. Review this project-file write after outside text; project files can be published later. Start a new session and reread private sources to restore tracking.' };
            }
            else if (credential) {
                if (publicEligible && presentation !== 'audit' && !c.labels.has('destructive'))
                    publicGrant = reservePublicRequest(paths, toolName, toolInput, written, policy, env);
                if (!publicGrant) {
                    reason = 'credential_egress';
                    sensitivePayload = true;
                    decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: 'WARDEN flow guard: review this project-file write after credentials and outside text. Short or encoded data can leave later through published files; an exact reviewed public request is required for automatic execution.' };
                }
            }
        }
    }
    if (!decision && tainted && c.labels.has('destructive') && !namedByUser(destinations(toolName, toolInput, policy, c.hosts), state.intent, state.intentRaw, state.resolvedVersion === 2 ? state.resolved : undefined) && !(destinations(toolName, toolInput, policy, c.hosts).length === 0 && keepsDestination(toolName, toolInput, policy))) {
        reason = 'destructive_action';
        decision = { permissionDecision: policy.mode === 'deny' ? 'deny' : 'ask', permissionDecisionReason: `WARDEN flow guard: the session read outside text (${sourcesText(state, defTaint)}); this call changes or deletes things outside the project. Allow it only if you expected it.` };
    }
    if (decision) {
        let targets = targetSummary(toolName, toolInput, policy, sensitivePayload);
        // The screen label is outside text: the prompt names only the guard's own word for it, never the label.
        const word = screen?.verb ?? screen?.destroy;
        if (word || screen?.via) {
            const ref = screen?.ref && /^[A-Za-z0-9_.:-]{1,24}$/.test(screen.ref) ? ` ${JSON.stringify(screen.ref)}` : '';
            const evidence = screen?.evidence === 'form' ? ` in a form with a "${word}" control; Enter may submit it`
                : screen?.evidence === 'identifier' ? ` whose accessibility identifier suggests "${word}"`
                    : screen?.evidence === 'semantic' ? ` reported as a "${word}" control`
                        : word ? ` whose label says "${word}"` : '';
            const via = screen?.via === 'coordinates' ? ' (coordinates intersect its reported geometry)'
                : screen?.via === 'focus' ? ' (reported focused element)' : '';
            const note = `screen element${ref}${evidence}${via}; last-snapshot context is untrusted, not a verified live target`;
            targets = targets.startsWith('not identified') ? note : `${note}; ${targets}`;
        }
        decision.permissionDecisionReason = `Action: ${safeToolName(toolName)}. Targets: ${targets}.\n${decision.permissionDecisionReason}`;
        // These are guard decisions, not proof a dialog was shown or a human clicked it. Never infer
        // approval from PostToolUse: execution can also follow automatic client permissions.
        const disposition = policy.mode === 'audit' || presentation === 'audit' ? 'audit_only'
            : decision.permissionDecision === 'deny' || presentation === 'refuse' ? 'refused' : 'approval_requested';
        log(paths, { event: 'pre', tool: safeToolName(toolName), decision: decision.permissionDecision, reason, disposition,
            approvalOutcome: 'unknown', mode: policy.mode, labels: [...c.labels] });
    }
    if (publicGrant)
        log(paths, { event: 'pre', tool: safeToolName(toolName), decision: 'allow', reason: 'credential_public_request', disposition: 'policy_allowed', approvalOutcome: 'unknown', mode: policy.mode });
    if (policy.mode === 'audit')
        return undefined;
    return decision;
}
/** What the person answered when `wrap` asked through the client (presentation `elicit`): the one case where the
 *  guard knows the outcome rather than inferring it. */
export function flowApproval(input, outcome, env = process.env) {
    if (!input.session_id || !input.tool_name)
        return;
    log(flowPaths(stateDir(env), input.session_id), { event: 'approval', tool: safeToolName(input.tool_name), approvalOutcome: outcome });
}
export function flowScreenValidation(input, outcome, env = process.env) {
    log(flowPaths(stateDir(env), input.session_id), { event: 'screen_validation', tool: safeToolName(input.tool_name), outcome });
}
