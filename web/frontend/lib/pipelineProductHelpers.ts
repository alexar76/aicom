/** Pure helpers for Pipeline Monitor product rows and tasks. */

import { PIPELINE_PRODUCT_STATES_FOR_FILTER } from '@/lib/pipelineFlow';

const PRODUCT_STATE_RANK: Record<string, number> = Object.fromEntries(
  PIPELINE_PRODUCT_STATES_FOR_FILTER.map((s, i) => [s, i]),
);

/** Pipeline state reached when a stage's agent completes its happy-path transition. */
export const STAGE_TARGET_STATE: Record<string, string> = {
  analyst: 'MARKET_RESEARCHED',
  pm: 'SPEC_WRITTEN',
  marketing: 'MARKET_CONTENT_READY',
  methodologist: 'METHODOLOGY_REVIEWED',
  architect: 'ARCH_DESIGNED',
  designer: 'DESIGN_CRITIQUED',
  developer: 'CODE_COMMITTED',
  qa: 'QA_TESTING',
  security: 'SECURITY_SCANNED',
  devops: 'SALES_ACTIVE',
  sales: 'SANDBOX_RUNNING',
};

const SHIPPED_PRODUCT_STATES = new Set([
  'SALES_ACTIVE',
  'SANDBOX_RUNNING',
  'TELEMETRY_COLLECTING',
  'EVOLUTION_ANALYZING',
  'COMPLETED',
  'DEPLOYED_PRODUCTION',
]);

function productStateRank(state: string): number {
  const key = String(state || '').toUpperCase();
  return PRODUCT_STATE_RANK[key] ?? -1;
}

export function isMaturePipelineProduct(product: Record<string, unknown>): boolean {
  const completedN = Number(
    (product.task_counts as { completed?: number } | undefined)?.completed ?? 0,
  );
  const pulseDone = Number(
    (product.pulse as { completed_stages?: number } | undefined)?.completed_stages ?? 0,
  );
  return completedN >= 40 || pulseDone >= 8;
}

export type PipelineStageStatus = 'completed' | 'running' | 'failed' | 'pending';

/** Infer stage tile status from product maturity when per-agent task rows were compacted. */
export function inferStageStatus(
  product: Record<string, unknown>,
  stage: string,
  taskList: Record<string, unknown>[],
): PipelineStageStatus {
  const task = findTaskForStage(taskList, stage);
  const direct = String(task?.status ?? '').toLowerCase();
  const pState = String(product.state ?? '').toUpperCase();
  const pRank = productStateRank(pState);
  const target = STAGE_TARGET_STATE[stage];
  const tRank = target ? productStateRank(target) : -1;
  const matureBuild = isMaturePipelineProduct(product);

  if (
    SHIPPED_PRODUCT_STATES.has(pState) ||
    (matureBuild && !['FAILED', 'CANCELLED', 'IDEA_RECEIVED'].includes(pState))
  ) {
    if (direct === 'running' && (stage === 'qa' || stage === 'developer')) return 'running';
    if (direct === 'failed') return 'failed';
    return 'completed';
  }

  if (tRank >= 0 && pRank > tRank) return 'completed';
  if (direct === 'failed') return 'failed';
  if (direct === 'running') return 'running';
  if (direct === 'completed') return 'completed';
  return 'pending';
}

export function syntheticTaskForStage(
  stage: string,
  status: PipelineStageStatus,
  productState: string,
): Record<string, unknown> {
  return {
    agent_type: stage === 'designer' ? 'architect' : stage,
    status,
    state: STAGE_TARGET_STATE[stage] ?? productState,
    synthetic: true,
    output_data: {
      summary:
        'Stage inferred from product maturity — historical task rows were compacted during repair / hardening loops.',
    },
  };
}

export function resolveStagePresentation(
  product: Record<string, unknown>,
  stage: string,
  taskList: Record<string, unknown>[],
): { status: PipelineStageStatus; task: Record<string, unknown> | null } {
  const status = inferStageStatus(product, stage, taskList);
  const task = findTaskForStage(taskList, stage);
  if (task) {
    const merged = { ...task };
    if (status !== 'pending' && String(task.status ?? '').toLowerCase() !== status) {
      merged.status = status;
    }
    return { status, task: merged };
  }
  if (status !== 'pending') {
    return {
      status,
      task: syntheticTaskForStage(stage, status, String(product.state ?? '')),
    };
  }
  return { status, task: null };
}

export function getFailureSummary(product: Record<string, unknown>): string[] {
  const lines: string[] = [];
  const primary = String(product?.failure_reason || '').trim();
  const lastError = String(product?.last_error || '').trim();
  const taskErrors = Array.isArray(product?.failed_task_errors)
    ? product.failed_task_errors.map((x: unknown) => String(x || '').trim()).filter(Boolean)
    : [];

  if (primary) lines.push(primary);
  if (lastError && !lines.includes(lastError)) lines.push(lastError);
  for (const err of taskErrors) {
    if (!lines.includes(err)) lines.push(err);
    if (lines.length >= 3) break;
  }
  if (lines.length === 0) {
    lines.push('Failure reason is not stored. Open failed task details.');
  }
  return lines.slice(0, 3);
}

export function toUnixSeconds(v: unknown): number | undefined {
  if (typeof v !== 'number' || !Number.isFinite(v)) return undefined;
  return v > 1e12 ? v / 1000 : v;
}

export function getLatestFailedTask(taskList: Record<string, unknown>[]): Record<string, unknown> | null {
  const failed = taskList.filter((t) => String(t?.status || '').toLowerCase() === 'failed');
  if (failed.length === 0) return null;
  const score = (t: Record<string, unknown>) => {
    const endAt = toUnixSeconds(t?.ended_at) || 0;
    const updatedAt = toUnixSeconds(t?.updated_at) || 0;
    const startAt = toUnixSeconds(t?.started_at) || 0;
    return endAt || updatedAt || startAt;
  };
  return failed.sort((a, b) => score(b) - score(a))[0] || null;
}

/** Short X-axis labels for per-agent cost bars (avoid naive slice cutting "developer" → "develo"). */
export function agentCostBarLabel(agentType: string): string {
  const k = agentType.toLowerCase().trim();
  const fixed: Record<string, string> = {
    developer: 'develop',
    dev: 'develop',
    methodologist: 'method',
    architect: 'arch',
    evolution_analyst: 'evolve',
  };
  if (fixed[k]) return fixed[k];
  if (k.length <= 8) return k;
  return k.slice(0, 8);
}

export function pipelineAgentEmoji(agentType: string): string {
  const icons: Record<string, string> = {
    analyst: '🔍',
    pm: '📋',
    architect: '🏗️',
    developer: '💻',
    dev: '💻',
    qa: '🧪',
    devops: '🚀',
    marketing: '📢',
    sales: '💰',
    security: '🛡️',
    evolution_analyst: '📈',
    designer: '🎨',
    methodologist: '🧭',
  };
  return icons[agentType] || '⚙️';
}

export function formatTaskDuration(start?: number, end?: number): string {
  if (!start || !end) return '';
  const secs = Math.round(end - start);
  if (secs < 1) return '<1s';
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export function formatTaskWhen(v: unknown): string {
  const s = toUnixSeconds(v);
  if (s === undefined) return '—';
  try {
    return new Date(s * 1000).toLocaleString();
  } catch {
    return String(v);
  }
}

export function safeJson(val: unknown, max = 48_000): string {
  try {
    const s = JSON.stringify(val, null, 2);
    if (s.length <= max) return s;
    return `${s.slice(0, max)}\n… (${s.length} chars total)`;
  } catch {
    return String(val);
  }
}

/** Match API task row to a pipeline stage (handles dev vs developer, etc.) */
export function findTaskForStage(
  taskList: Record<string, unknown>[],
  stage: string,
): Record<string, unknown> | undefined {
  if (stage === 'designer') {
    return taskList.find(
      (x) => x.agent_type === 'architect' || x.agent_type === 'landing_architect',
    );
  }
  if (stage === 'methodologist') {
    const direct = taskList.find((x) => x.agent_type === 'methodologist');
    if (direct) return direct;
    const pm = taskList.find((x) => x.agent_type === 'pm');
    const qa = taskList.find((x) => x.agent_type === 'qa');
    const pmReview = (pm?.result as Record<string, unknown> | undefined)?.methodology_spec_review
      || (pm?.data as Record<string, unknown> | undefined)?.methodology_spec_review;
    const qaReview = (qa?.result as Record<string, unknown> | undefined)?.methodology_review
      || (qa?.data as Record<string, unknown> | undefined)?.methodology_review;
    const pmPassed = pmReview ? !!(pmReview as { passed?: boolean }).passed : null;
    const qaPassed = qaReview ? !!(qaReview as { passed?: boolean }).passed : null;
    let status = 'pending';
    if (pmPassed === false || qaPassed === false) status = 'failed';
    else if (pm?.status === 'running' || qa?.status === 'running') status = 'running';
    else if (pmPassed === true || qaPassed === true) status = 'completed';
    else if (pm?.status === 'completed') status = 'completed';
    return {
      agent_type: 'methodologist',
      status,
      data: { methodology_spec_review: pmReview, methodology_review: qaReview },
    };
  }
  const t = taskList.find((x) => x.agent_type === stage);
  if (t) return t;
  if (stage === 'developer') {
    return taskList.find(
      (x) => x.agent_type === 'dev' || x.agent_type === 'landing_developer',
    );
  }
  if (stage === 'dev') {
    return taskList.find(
      (x) => x.agent_type === 'developer' || x.agent_type === 'landing_developer',
    );
  }
  return undefined;
}
