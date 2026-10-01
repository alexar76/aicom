import type { AdminLocale } from '@/lib/adminI18n';
import { t, tVars } from '@/lib/adminI18n';
import type { ProductPulsePayload } from '@/components/admin/tabs/ProductPulse';
import type { PipelineCatalogProduct } from '@/components/admin/pipeline/PipelineProductList';

export type PipelineVitalsQualitySource =
  | 'human_score'
  | 'demo_score'
  | 'qa_gates'
  | 'none';

export type PipelineProductVitals = {
  productId: string;
  productLabel: string;
  state: string;
  costUsd: number;
  costCapUsd: number;
  costPct: number | null;
  costDetail: string;
  llmCalls: number;
  llmTokens: number;
  progressPct: number | null;
  progressDetail: string;
  completedStages: number | null;
  totalStages: number | null;
  qualityPct: number | null;
  qualityDetail: string;
  qualitySource: PipelineVitalsQualitySource;
};

function productLabel(product: PipelineCatalogProduct): string {
  return product.spec?.product_name || product.idea || product.id;
}

const REPAIR_STATES = new Set(['DEV_FIXING', 'BUG_FOUND', 'QA_TESTING', 'CODE_TESTING']);

/** Stage dots during repair reflect historical agents, not “% until ship” — use tasks/ETA instead. */
function pulseStagesTrustworthy(state: string, pulse: ProductPulsePayload | undefined): boolean {
  if (REPAIR_STATES.has(state)) return false;
  if (!pulse || typeof pulse.completed_stages !== 'number' || typeof pulse.total_stages !== 'number') {
    return false;
  }
  return pulse.total_stages > 0;
}

export function computePipelineProductVitals(
  product: PipelineCatalogProduct,
  locale: AdminLocale,
): PipelineProductVitals {
  const eco = (product.economics || {}) as Record<string, unknown>;
  const pulse = product.pulse as ProductPulsePayload | undefined;
  const state = String(product.state || 'UNKNOWN').toUpperCase();

  const costUsd = Number(eco.llm_cost_usd) || 0;
  const costCapUsd = Number(eco.pipeline_cost_cap_usd) || 0;
  const llmCalls = Number(eco.llm_call_count) || 0;
  const llmTokens = Number(eco.llm_total_tokens) || 0;
  const costPct = costCapUsd > 0 ? Math.min(100, (costUsd / costCapUsd) * 100) : null;

  let costDetail: string;
  if (llmCalls > 0) {
    costDetail = tVars(locale, 'pipeline.vitals.costCallsTokens', {
      calls: String(llmCalls),
      tokens: llmTokens.toLocaleString(),
    });
  } else if (costUsd > 0) {
    costDetail = t(locale, 'pipeline.vitals.costFromLog');
  } else {
    costDetail = t(locale, 'pipeline.vitals.costNoLog');
  }

  let progressPct: number | null = null;
  let progressDetail = t(locale, 'pipeline.vitals.progressUnknown');
  let completedStages: number | null = null;
  let totalStages: number | null = null;

  if (
    state === 'COMPLETED' ||
    state === 'DEPLOYED_PRODUCTION' ||
    state === 'FAILED' ||
    state === 'CANCELLED'
  ) {
    progressPct = 100;
    progressDetail =
      state === 'FAILED'
        ? t(locale, 'pipeline.vitals.deadlineDoneFailed')
        : state === 'CANCELLED'
          ? t(locale, 'pipeline.vitals.progressCancelled')
          : t(locale, 'pipeline.vitals.deadlineDone');
    if (typeof pulse?.completed_stages === 'number' && typeof pulse?.total_stages === 'number') {
      completedStages = pulse.completed_stages;
      totalStages = pulse.total_stages;
    }
  } else if (REPAIR_STATES.has(state)) {
    const tc = product.task_counts;
    const total = Number(tc?.total) || 0;
    const done = Number(tc?.completed) || 0;
    if (total > 0) {
      progressPct = Math.min(100, Math.max(0, Math.round((done / total) * 100)));
      progressDetail = tVars(locale, 'pipeline.vitals.progressRepairTasks', {
        done: String(done),
        total: String(total),
        state,
      });
    } else if (pulse?.eta_label) {
      progressDetail = tVars(locale, 'pipeline.vitals.progressRepairEta', {
        eta: pulse.eta_label,
        state,
      });
    }
  } else if (
    typeof pulse?.completed_stages === 'number' &&
    typeof pulse?.total_stages === 'number' &&
    pulse.total_stages > 0
  ) {
    completedStages = pulse.completed_stages;
    totalStages = pulse.total_stages;
    progressPct = Math.min(100, Math.max(0, Math.round((completedStages / totalStages) * 100)));
    progressDetail = tVars(locale, 'pipeline.vitals.progressStages', {
      done: String(completedStages),
      total: String(totalStages),
    });
  } else {
    const tc = product.task_counts;
    const total = Number(tc?.total) || 0;
    const done = Number(tc?.completed) || 0;
    if (total > 0) {
      progressPct = Math.min(100, Math.max(0, Math.round((done / total) * 100)));
      progressDetail = tVars(locale, 'pipeline.vitals.progressTasks', {
        done: String(done),
        total: String(total),
      });
    }
  }

  let qualityPct: number | null = null;
  let qualityDetail = t(locale, 'pipeline.vitals.qualityUnknown');
  let qualitySource: PipelineVitalsQualitySource = 'none';

  const humanRaw = eco.quality_score ?? pulse?.quality_score;
  if (typeof humanRaw === 'number' && Number.isFinite(humanRaw) && humanRaw > 0) {
    const clamped = Math.min(5, Math.max(0, humanRaw));
    qualityPct = Math.round((clamped / 5) * 100);
    qualityDetail = tVars(locale, 'pipeline.vitals.qualityHuman', { score: String(clamped) });
    qualitySource = 'human_score';
  } else {
    const demo = (product as { demo_quality?: { score?: number } }).demo_quality;
    const demoScore = demo?.score;
    if (typeof demoScore === 'number' && Number.isFinite(demoScore)) {
      qualityPct = Math.min(100, Math.max(0, Math.round(demoScore)));
      qualityDetail = tVars(locale, 'pipeline.vitals.qualityDemo', { score: String(Math.round(demoScore)) });
      qualitySource = 'demo_score';
    } else if (product.qa_gates_all_passed === true) {
      qualityPct = 100;
      qualityDetail = t(locale, 'pipeline.vitals.qualityQaPass');
      qualitySource = 'qa_gates';
    } else if (product.qa_gates_all_passed === false) {
      qualityPct = 0;
      qualityDetail = t(locale, 'pipeline.vitals.qualityQaFail');
      qualitySource = 'qa_gates';
    } else if (pulse?.quality_pulse === 'green') {
      qualityPct = 100;
      qualityDetail = pulse?.quality_hint?.slice(0, 56) || t(locale, 'pipeline.vitals.qualityQaPass');
      qualitySource = 'qa_gates';
    } else if (pulse?.quality_pulse === 'red') {
      qualityPct = 0;
      qualityDetail = pulse?.quality_hint?.slice(0, 56) || t(locale, 'pipeline.vitals.qualityQaFail');
      qualitySource = 'qa_gates';
    } else if (pulse?.quality_hint) {
      qualityDetail = pulse.quality_hint.slice(0, 56);
    }
  }

  return {
    productId: product.id,
    productLabel: productLabel(product),
    state,
    costUsd,
    costCapUsd,
    costPct,
    costDetail,
    llmCalls,
    llmTokens,
    progressPct,
    progressDetail,
    completedStages,
    totalStages,
    qualityPct,
    qualityDetail,
    qualitySource,
  };
}

export function formatVitalsPercent(pct: number | null): string {
  if (pct == null || !Number.isFinite(pct)) return '—';
  return `${Math.round(pct)}%`;
}

export function formatVitalsUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return '$0.00';
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}
