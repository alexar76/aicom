// GENERATED from src/flow-guard.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/**
 * Flow guard: break the "lethal trifecta" inside a running Claude Code session.
 *
 * Detecting injected instructions is a guess; the same sentence can be reworded,
 * translated or hidden in data. What can be enforced is the combination that makes an
 * injection costly: in one session the agent (1) reads text written by someone else,
 * (2) reads the user's private data and (3) sends something off the machine. Text that
 * arrives through (1) can then tell the model to read with (2) and send with (3).
 *
 * The guard watches every tool call through Claude Code's hooks and keeps per-session
 * state. Once outside text is in the context ("tainted"), and private data has been read,
 * a call that can send data out asks the user first (or is denied, by mode). Independently,
 * a call that carries text the session read from private files is caught by fingerprint:
 * secrets are denied outright, other private text asks. A tool call that would change the
 * guard's own policy or Claude Code's hook settings never passes silently.
 *
 * It does not read the model's mind and does not need to recognise an attack. What it
 * cannot see: prompts submitted before installation, text the model already holds from before the hook was
 * installed, and harm that needs no outbound or destructive call (a wrong answer). For that last one the
 * Stop hook can only tell the user which outside text the answer drew on.
 *
 * Dependency-free on purpose (node: built-ins only): the Claude Code plugin runs a copy of
 * the compiled files on every tool call (claude-plugin/scripts/flow-guard*.mjs; a test keeps
 * each copy identical to its dist/flow-guard*.js).
 *
 * This file is the public API and the hook entry point. The parts are flow-guard-*.ts: the shared
 * types, state paths, operator policy, text extraction, call classification, screen tools,
 * destinations, fingerprints, decoding, credential fragments, leak checks, session state, the
 * PreToolUse and PostToolUse hooks, the prompt and Stop hooks (answer), and the flow-labels report.
 */
import { readFileSync } from 'node:fs';
import { flowPre } from './flow-guard-pre.mjs';
import { flowPost } from './flow-guard-post.mjs';
import { flowPrompt, flowStop } from './flow-guard-answer.mjs';
export { stateDir, flowPaths, isSecretPath, isProtectedPath } from './flow-guard-paths.mjs';
export { DEFAULT_POLICY, loadPolicy, readPinnedTaskManifest, publicRequestDigest, hostMatches } from './flow-guard-policy.mjs';
export { hostsIn } from './flow-guard-text.mjs';
export { classifyShell, classifyCall, resultTaints } from './flow-guard-classify.mjs';
export { screenFromResult, screenCall, screenObservation, screenTargetEvidence, screenTargetStamp, screenResponseEvidence, screenResponseStamp, screenSecretRead } from './flow-guard-screen.mjs';
export { destinations, keepsDestination, resolvedContacts, namedByUser } from './flow-guard-destinations.mjs';
export { normalizeText, fingerprints, piiTokens, secretPattern, secretValues, secretTokens, tokenFingerprints, tokenWindows } from './flow-guard-fingerprints.mjs';
export { spelledCandidates, characterCodeCandidates, natoCandidates, scanCandidates, candidates } from './flow-guard-decode.mjs';
export { fragmentFingerprints, checkFragments } from './flow-guard-fragments.mjs';
export { checkLeak, checkStream } from './flow-guard-leak.mjs';
export { readFlowState, updateFlowState, flowStateExists } from './flow-guard-state.mjs';
export { flowPre, flowApproval, flowScreenValidation } from './flow-guard-pre.mjs';
export { flowPost } from './flow-guard-post.mjs';
export { ownWords, flowPrompt, instructionText, lastAnswer, flowStop } from './flow-guard-answer.mjs';
export { unlabeledTools, flowLabelsReport } from './flow-guard-labels.mjs';
/** Hook runner shared by the CLI and the plugin script: `pre`, `post`, `prompt` or `stop`, hook JSON on stdin, decision JSON on stdout. */
export function runFlowHook(event, stdin, env = process.env) {
    let input;
    try {
        input = JSON.parse(stdin || '{}');
    }
    catch {
        return undefined;
    }
    if (!input || typeof input !== 'object' || Array.isArray(input))
        return undefined;
    if (event === 'pre') {
        const d = flowPre(input, env);
        return d ? JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', ...d } }) : undefined;
    }
    if (event === 'prompt') {
        flowPrompt(input, env);
        return undefined;
    }
    if (event === 'stop') {
        const o = flowStop(input, env);
        return o ? JSON.stringify(o) : undefined;
    }
    if (event === 'post') {
        const o = flowPost(input, env);
        if (!o)
            return undefined;
        return JSON.stringify({ ...(o.systemMessage ? { systemMessage: o.systemMessage } : {}), ...(o.additionalContext ? { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: o.additionalContext } } : {}) });
    }
    return undefined;
}
export function flowGuardMain(argv = process.argv.slice(2)) {
    const event = argv[0] || '';
    let stdin = '';
    try {
        stdin = readFileSync(0, 'utf8');
    }
    catch {
        return;
    }
    try {
        const out = runFlowHook(event, stdin);
        if (out)
            process.stdout.write(out + '\n');
    }
    catch (err) {
        // Never interpret corrupt/unreadable state as permission to execute a tool.
        process.stderr.write(`warden flow guard: ${err instanceof Error ? err.message : String(err)}\n`);
        if (event === 'pre')
            process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: 'WARDEN flow guard could not safely check this call. Repair the guard state before retrying.' } }) + '\n');
    }
}
