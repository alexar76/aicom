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

/**
 * Single-flight, because three independent consumers ask for this at once.
 *
 * DashboardTab's effect calls `prefetchAdminDashboard()` and then `loadAdminDashboardLayers()`
 * itself, back to back; `useMonitorMetrics` calls it too. The prefetch has an `inflight` guard
 * but it guards only the prefetch, so one dashboard render issued the whole layer sequence
 * twice: pipeline-summary ×2, quick ×2, full ×2 — measured as /api/admin/dashboard four times
 * in 18 requests for 11 distinct endpoints. With the HTTP firewall allowing 100 requests per
 * minute per IP across every route, that is how the console rate-limited itself into 403s.
 *
 * A shared promise is the fix rather than a cache: callers that overlap get the same load, and
 * once it settles the next caller starts a fresh one, so nothing is ever served stale.
 */
let layersInFlight: Promise<DashboardLoadResult> | null = null;
let fullInFlight: Promise<DashboardData | null> | null = null;

/** Fast path: pipeline SQL totals + quick dashboard (same order as Dashboard / Monitor). */
export function loadAdminDashboardLayers(): Promise<DashboardLoadResult> {
  if (layersInFlight) return layersInFlight;
  layersInFlight = loadAdminDashboardLayersUncoalesced().finally(() => {
    layersInFlight = null;
  });
  return layersInFlight;
}

async function loadAdminDashboardLayersUncoalesced(): Promise<DashboardLoadResult> {
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
export function loadAdminDashboardFull(): Promise<DashboardData | null> {
  if (fullInFlight) return fullInFlight;
  fullInFlight = loadAdminDashboardFullUncoalesced().finally(() => {
    fullInFlight = null;
  });
  return fullInFlight;
}

async function loadAdminDashboardFullUncoalesced(): Promise<DashboardData | null> {
  try {
    const full = await api.getDashboard(false);
    const next = { ...full, dashboard_partial: false };
    return persist(next);
  } catch {
    return readAdminMetricsCache();
  }
}
