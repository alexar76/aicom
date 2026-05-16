/** Pure helpers for Pipeline Monitor product rows and tasks. */

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
    return taskList.find((x) => x.agent_type === 'architect');
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
    return taskList.find((x) => x.agent_type === 'dev');
  }
  if (stage === 'dev') {
    return taskList.find((x) => x.agent_type === 'developer');
  }
  return undefined;
}
