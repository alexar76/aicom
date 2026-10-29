#!/usr/bin/env node
// WARDEN PreToolUse hook for Claude Code — no dependencies, no network, no child processes.
//
// Reads the verdicts `warden-mcp hook session-start` recorded for this session and denies a
// call to an mcp__<server>__<tool> tool whose server or tool WARDEN blocked. It must agree with
// `decide()` in @aimarket/warden (src/claude-hook.ts); test/claude-plugin.test.ts runs both on
// the same cases. A failure here never blocks: it prints nothing and exits 0.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const normalizeName = name => name.replace(/[^a-zA-Z0-9_-]/g, '_');
const contextSafeName = name => /^[A-Za-z0-9_.:-]{1,64}$/.test(name) ? name : '(name withheld)';
const stateDir = () => process.env.WARDEN_STATE_DIR || join(process.env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'warden');

export function decide(toolName, verdicts, strict) {
  if (!toolName.startsWith('mcp__')) return undefined;
  if (!verdicts) return strict ? { permissionDecision: 'ask', permissionDecisionReason: 'WARDEN has no session-start scan for this session.' } : undefined;
  let best;
  for (const s of verdicts.servers) {
    if (toolName.startsWith(`mcp__${s.normalized}__`) && (!best || s.normalized.length > best.normalized.length)) best = s;
  }
  if (!best) return strict ? { permissionDecision: 'ask', permissionDecisionReason: 'WARDEN did not vet the MCP server behind this tool (it is not in .mcp.json or ~/.claude.json).' } : undefined;
  const tool = toolName.slice(`mcp__${best.normalized}__`.length);
  if (best.allow === false) {
    return { permissionDecision: 'deny', permissionDecisionReason: `WARDEN blocked MCP server "${contextSafeName(best.key)}" at session start (${best.codes.slice(0, 6).join(', ') || 'see warden-mcp scan'}). Review it with: warden-mcp scan` };
  }
  if (best.blockedTools.some(t => normalizeName(t) === tool)) {
    return { permissionDecision: 'deny', permissionDecisionReason: `WARDEN blocked this tool of MCP server "${contextSafeName(best.key)}" at session start. Review it with: warden-mcp scan` };
  }
  if (best.status === 'error' && strict) return { permissionDecision: 'ask', permissionDecisionReason: `WARDEN could not check MCP server "${contextSafeName(best.key)}" at session start.` };
  return undefined;
}

function main() {
  let input;
  try { input = JSON.parse(readFileSync(0, 'utf8') || '{}'); } catch { return; }
  const toolName = typeof input.tool_name === 'string' ? input.tool_name : '';
  if (!toolName.startsWith('mcp__')) return;
  const sessionId = typeof input.session_id === 'string' ? input.session_id : '';
  let verdicts;
  try {
    if (sessionId) verdicts = JSON.parse(readFileSync(join(stateDir(), 'claude-code', 'sessions', createHash('sha256').update(sessionId).digest('hex') + '.json'), 'utf8'));
  } catch { verdicts = undefined; }
  if (verdicts && verdicts.version !== 1) verdicts = undefined;
  const decision = decide(toolName, verdicts, process.env.WARDEN_HOOK_STRICT === '1');
  if (decision) process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', ...decision } }) + '\n');
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith('pre-tool-use.mjs')) {
  try { main(); } catch { /* never block on our own failure */ }
}
