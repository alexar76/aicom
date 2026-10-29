// GENERATED from src/flow-guard-labels.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: `warden-mcp flow-labels`, the MCP tools sessions used without an operator label. */
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { flowPaths, stateDir } from './flow-guard-paths.mjs';
import { LABELS } from './flow-guard-policy.mjs';
import { readFlowState, safeToolName } from './flow-guard-state.mjs';
/** MCP tools that sessions used without an operator label, with the guard's guess and the sessions that used them. */
export function unlabeledTools(env = process.env) {
    const dir = flowPaths(stateDir(env), 'x').dir;
    const seen = new Map();
    let files = [];
    try {
        files = readdirSync(dir).filter(f => /^[0-9a-f]{64}\.json$/.test(f));
    }
    catch {
        return [];
    }
    for (const f of files) {
        let s;
        try {
            s = readFlowState(join(dir, f));
        }
        catch {
            continue;
        }
        for (const [tool, labels] of Object.entries(s.unlabeled ?? {})) {
            const e = seen.get(tool) ?? { guessed: new Set(), sessions: 0 };
            for (const l of labels)
                e.guessed.add(l);
            e.sessions++;
            seen.set(tool, e);
        }
    }
    return [...seen].map(([tool, e]) => ({ tool, guessed: LABELS.filter(l => e.guessed.has(l)), sessions: e.sessions })).sort((a, b) => b.sessions - a.sessions || a.tool.localeCompare(b.tool));
}
/** `warden-mcp flow-labels`: the unlabeled tools, and a labels block to review and paste into the policy file. */
export function flowLabelsReport(env = process.env) {
    const tools = unlabeledTools(env);
    const policyPath = env.WARDEN_FLOW_POLICY || join(stateDir(env), 'flow-policy.json');
    if (!tools.length)
        return `No MCP tool without a label has been used in a recorded session. Policy file: ${policyPath}\n`;
    const lines = tools.map(t => `  ${safeToolName(t.tool).padEnd(48)} guessed: ${t.guessed.join(', ') || '-'}   sessions: ${t.sessions}`);
    const labels = Object.fromEntries(tools.map(t => [t.tool, t.guessed]));
    return [
        `MCP tools used without an operator label (${tools.length}). The guard guessed from names and arguments; a guess only adds caution.`,
        ...lines,
        '',
        `Check each guess against what the tool really does, then put the corrected labels into ${policyPath}:`,
        '  private: returns the user\'s own data   untrusted: returns text others wrote   outbound: reaches a person or a host   destructive: changes or deletes things',
        '',
        JSON.stringify({ labels }, null, 2),
        '',
    ].join('\n');
}
