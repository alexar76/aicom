/**
 * Instant dashboard pipeline totals from Pipeline Monitor localStorage (same source as catalog).
 */

import type { DashboardData } from '@/lib/api';
import {
  readPipelineCatalogCache,
  readPipelineCatalogPeek,
  type PipelineCatalogSummaryCached,
} from '@/lib/pipelineCatalogCache';

function summaryToPipeline(
  summary: PipelineCatalogSummaryCached,
): DashboardData['pipeline'] {
  const total = summary.total_products;
  const completed = summary.shipped_products;
  const failed = summary.failed_products;
  const active = Math.max(0, total - completed - failed);
  return {
    total_products: total,
    active_products: active,
    completed_products: completed,
    failed_products: failed,
    pending_tasks: 0,
    running_tasks: 0,
    timed_out_tasks: 0,
    storefront_visible_products: summary.storefront_listable_products ?? null,
    state_distribution: {},
    failed_alerts: [],
  };
}

/** Read catalog summary written by Pipeline tab (peek first — smallest, fastest). */
export function readPipelineCatalogSummaryForDashboard(): PipelineCatalogSummaryCached | null {
  if (typeof window === 'undefined') return null;
  for (const sort of ['shipped_first', 'newest'] as const) {
    const peek = readPipelineCatalogPeek(sort);
    if (peek?.catalog_summary && peek.catalog_summary.total_products > 0) {
      return peek.catalog_summary;
    }
    const full = readPipelineCatalogCache(sort);
    if (full?.catalog_summary && full.catalog_summary.total_products > 0) {
      return full.catalog_summary;
    }
  }
  return null;
}

export function mergePipelineSummaryIntoDashboard(
  data: DashboardData,
  summary: PipelineCatalogSummaryCached,
): DashboardData {
  return {
    ...data,
    dashboard_partial: data.dashboard_partial ?? true,
    pipeline: {
      ...data.pipeline,
      ...summaryToPipeline(summary),
      storefront_visible_products:
        data.pipeline.storefront_visible_products ??
        summary.storefront_listable_products ??
        null,
    },
  };
}

/** Prefer non-zero pipeline totals from catalog cache when admin metrics are still empty. */
export function hydrateDashboardFromPipelineCache(data: DashboardData): DashboardData {
  const summary = readPipelineCatalogSummaryForDashboard();
  if (!summary) return data;
  if ((data.pipeline?.total_products ?? 0) > 0) return data;
  return mergePipelineSummaryIntoDashboard(data, summary);
}
