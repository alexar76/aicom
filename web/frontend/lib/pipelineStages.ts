/**
 * Pipeline stage helpers for Admin UI.
 * Flow constants live in `pipelineFlow.ts` (SSOT: `config/pipeline_flow.json`).
 */
export {
  PIPELINE_STAGE_ORDER,
  PIPELINE_PRODUCT_STATES_FOR_FILTER,
  AGENTS_TAB_ORDER,
  PIPELINE_AGENT_FLOW,
  pipelineStateLabel,
  pipelineStateColor,
  pipelineHappyPathStates,
  type PipelineStageType,
  type AgentsTabType,
} from './pipelineFlow';

import { AGENTS_TAB_ORDER } from './pipelineFlow';

export interface AgentLogMetricsSlice {
  total_entries: number;
  recent_entries: number;
  recent_errors: number;
  last_active: number;
  status: string;
}

export interface AgentRowInput {
  type: string;
  status: string;
  current_task: string | null;
  uptime: number;
  tasks_completed: number;
  timeout?: number;
  last_active?: number | null;
  log_metrics?: AgentLogMetricsSlice | null;
}

const emptyRow = (type: string): AgentRowInput => ({
  type,
  status: 'idle',
  current_task: null,
  uptime: 0,
  tasks_completed: 0,
});

/**
 * Always includes Designer after Architect (mirrors Architect counts/status).
 * Fills missing tab types with idle zeros so the roster matches the pipeline.
 */
export function buildAgentsTabRows(fromApi: AgentRowInput[]): AgentRowInput[] {
  const map = new Map<string, AgentRowInput>();
  for (const t of AGENTS_TAB_ORDER) {
    map.set(t, emptyRow(t));
  }
  for (const a of fromApi) {
    if (!a?.type) continue;
    const base = map.get(a.type) ?? emptyRow(a.type);
    map.set(a.type, {
      ...base,
      ...a,
      type: a.type,
      tasks_completed: Number(a.tasks_completed) || 0,
      uptime: Number(a.uptime) || 0,
    });
  }
  const arch = map.get('architect');
  const des = map.get('designer') ?? emptyRow('designer');
  map.set('designer', {
    ...des,
    type: 'designer',
    tasks_completed: Math.max(des.tasks_completed, arch?.tasks_completed ?? 0),
    status: arch?.status || des.status || 'idle',
    uptime: arch?.uptime ?? des.uptime ?? 0,
    current_task: des.current_task ?? arch?.current_task ?? null,
    last_active: des.last_active ?? arch?.last_active ?? null,
    timeout:
      typeof des.timeout === 'number' && des.timeout > 0
        ? des.timeout
        : typeof arch?.timeout === 'number'
          ? arch.timeout
          : des.timeout,
    log_metrics: des.log_metrics ?? arch?.log_metrics ?? null,
  });
  return AGENTS_TAB_ORDER.map((t) => map.get(t)!);
}

/** Pre-fetch roster for Admin → AI Agents (all stages + Designer). */
export const INITIAL_AGENTS_TAB_ROWS: AgentRowInput[] = buildAgentsTabRows([]);
