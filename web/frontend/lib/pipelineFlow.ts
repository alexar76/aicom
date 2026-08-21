/**
 * Pipeline flow SSOT — loaded from `config/pipeline_flow.json` (shared with Python orchestrator).
 */
import flowDoc from '../../../config/pipeline_flow.json';

type FlowDoc = {
  agent_flow: Record<string, [string, string]>;
  stage_agents: string[];
  agents_tab_extra?: string[];
  product_states: string[];
  state_labels: Record<string, string>;
  state_colors: Record<string, string>;
};

const doc = flowDoc as unknown as FlowDoc;

/** state → [agent, next_state] (happy-path worker flow). */
export const PIPELINE_AGENT_FLOW: Record<string, readonly [string, string]> = Object.freeze(
  Object.fromEntries(
    Object.entries(doc.agent_flow).map(([state, pair]) => [state, [pair[0], pair[1]] as const]),
  ),
);

/** Admin pipeline monitor / diagrams — core agent stages in order. */
export const PIPELINE_STAGE_ORDER = Object.freeze([...doc.stage_agents]) as readonly string[];

export type PipelineStageType = (typeof PIPELINE_STAGE_ORDER)[number];

/** Admin → AI Agents tab order (pipeline stages + evolution meta-agent). */
export const AGENTS_TAB_ORDER = Object.freeze([
  ...doc.stage_agents,
  ...(doc.agents_tab_extra ?? []),
]) as readonly string[];

export type AgentsTabType = (typeof AGENTS_TAB_ORDER)[number];

/** Product lifecycle states for filters (matches orchestrator + SQLite). */
export const PIPELINE_PRODUCT_STATES_FOR_FILTER: readonly string[] = Object.freeze([
  ...doc.product_states,
]);

export function pipelineStateLabel(state: string): string {
  const key = String(state || '').toUpperCase();
  return doc.state_labels[key] ?? key;
}

export function pipelineStateColor(state: string): string {
  const key = String(state || '').toUpperCase();
  return doc.state_colors[key] ?? '#6b7280';
}

/** Ordered states along the happy path (for progress UI). */
export function pipelineHappyPathStates(): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  let cursor: string | undefined = 'IDEA_RECEIVED';
  while (cursor && PIPELINE_AGENT_FLOW[cursor]) {
    if (!seen.has(cursor)) {
      seen.add(cursor);
      ordered.push(cursor);
    }
    const next: string = PIPELINE_AGENT_FLOW[cursor][1];
    if (seen.has(next)) break;
    cursor = next;
  }
  if (!seen.has('COMPLETED')) ordered.push('COMPLETED');
  return ordered;
}
