/**
 * Canonical pipeline stage order (Admin Pipeline Monitor, public diagrams).
 * Designer = UX layer from architecture (same worker output as Architect task).
 * Methodologist = dedicated post-marketing methodology snapshot before architecture.
 */
export const PIPELINE_STAGE_ORDER = [
  'analyst',
  'pm',
  'marketing',
  'methodologist',
  'architect',
  'designer',
  'developer',
  'qa',
  'security',
  'devops',
  'sales',
] as const;

export type PipelineStageType = (typeof PIPELINE_STAGE_ORDER)[number];

/** Admin → AI Agents tab: same core order + evolution meta-agent + methodologist gate. */
export const AGENTS_TAB_ORDER = [
  'analyst',
  'pm',
  'marketing',
  'methodologist',
  'architect',
  'designer',
  'developer',
  'qa',
  'security',
  'devops',
  'sales',
  'evolution_analyst',
] as const;

export type AgentsTabType = (typeof AGENTS_TAB_ORDER)[number];

export interface AgentRowInput {
  type: string;
  status: string;
  current_task: string | null;
  uptime: number;
  tasks_completed: number;
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
    tasks_completed: Math.max(
      des.tasks_completed,
      arch?.tasks_completed ?? 0
    ),
    status: arch?.status || des.status || 'idle',
    uptime: arch?.uptime ?? des.uptime ?? 0,
  });
  return AGENTS_TAB_ORDER.map((t) => map.get(t)!);
}

/** Pre-fetch roster for Admin → AI Agents (all stages + Designer). */
export const INITIAL_AGENTS_TAB_ROWS: AgentRowInput[] = buildAgentsTabRows([]);

/**
 * Product lifecycle states for Admin → Pipeline Monitor state filter.
 * Matches orchestrator `PipelineState` (+ deployment alias). Union with on-screen
 * data so legacy / rare states still appear.
 */
export const PIPELINE_PRODUCT_STATES_FOR_FILTER: readonly string[] = [
  'IDEA_RECEIVED',
  'MARKET_RESEARCHED',
  'SPEC_WRITTEN',
  'MARKET_CONTENT_READY',
  'METHODOLOGY_REVIEWED',
  'ARCH_DESIGNED',
  'DESIGN_CRITIQUED',
  'CODE_COMMITTED',
  'CODE_TESTING',
  'QA_TESTING',
  'BUG_FOUND',
  'DEV_FIXING',
  'SECURITY_SCANNED',
  'HUMAN_REVIEW_PENDING',
  'SALES_ACTIVE',
  'SANDBOX_RUNNING',
  'TELEMETRY_COLLECTING',
  'EVOLUTION_ANALYZING',
  'COMPLETED',
  'DEPLOYED_PRODUCTION',
  'FAILED',
  'CANCELLED',
];
