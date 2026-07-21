/**
 * Shared admin dashboard load order (Pipeline-aligned counts first, full payload later).
 */

import api, { type DashboardData } from '@/lib/api';
import {
  bootDashboardData,
  mergeDashboardQuick,
  readAdminMetricsCache,
  shouldWriteAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';
import { hydrateDashboardFromPipelineCache } from '@/lib/dashboardPipelineBootstrap';

export type DashboardLoadResult = {
  /** Best snapshot after pipeline-summary + quick (may still be partial). */
  snapshot: DashboardData;
  /** True when pipeline-summary or quick returned authoritative totals. */
  pipelineCountsReady: boolean;
  /** True after quick/full sampled CPU, memory, disk (pipeline-summary alone is not enough). */
  systemMetricsReady: boolean;
};

function persist(patch: DashboardData): DashboardData {
  const next = hydrateDashboardFromPipelineCache(patch);
  if (shouldWriteAdminMetricsCache(next)) {
    writeAdminMetricsCache(next);
  }
  return next;
}

/** Fast path: pipeline SQL totals + quick dashboard (same order as Dashboard / Monitor). */
export async function loadAdminDashboardLayers(): Promise<DashboardLoadResult> {
  let snapshot = bootDashboardData();
  let pipelineCountsReady = snapshot.pipeline.total_products > 0;
  let systemMetricsReady = !snapshot.dashboard_partial;

  try {
    const summary = await api.getDashboardPipelineSummary();
    snapshot = persist({
      ...snapshot,
      pipeline: { ...snapshot.pipeline, ...summary },
    });
    pipelineCountsReady = snapshot.pipeline.total_products > 0;
  } catch {
    /* quick / cache may still update */
  }

  try {
    const quick = await api.getDashboard(true);
    snapshot = persist(mergeDashboardQuick(readAdminMetricsCache() ?? snapshot, quick));
    pipelineCountsReady =
      pipelineCountsReady || snapshot.pipeline.total_products > 0;
    systemMetricsReady = true;
  } catch {
    /* pipeline-summary / cache may still update */
  }

  return { snapshot, pipelineCountsReady, systemMetricsReady };
}

/** Background refresh — agents, heatmap, factory floor, storefront scan. */
export async function loadAdminDashboardFull(): Promise<DashboardData | null> {
  try {
    const full = await api.getDashboard(false);
    const next = { ...full, dashboard_partial: false };
    return persist(next);
  } catch {
    return readAdminMetricsCache();
  }
}
