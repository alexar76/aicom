/**
 * Shared localStorage snapshot for Admin dashboard + Live Monitor metrics.
 * Same payload shape as GET /api/admin/dashboard (full) and SSE metrics stream.
 */

import type { DashboardData } from '@/lib/api';
import { hydrateDashboardFromPipelineCache } from '@/lib/dashboardPipelineBootstrap';

export const ADMIN_METRICS_CACHE_KEY = 'aicom_admin_dashboard_swr_v5';

function isCachedMetricsPayload(x: unknown): x is DashboardData {
  if (!x || typeof x !== 'object') return false;
  const o = x as DashboardData;
  if (
    o.dashboard_partial &&
    (o.pipeline?.total_products ?? 0) === 0 &&
    !o.dashboard_build_degraded
  ) {
    return false;
  }
  return (
    o.pipeline != null &&
    typeof o.pipeline.total_products === 'number' &&
    o.resources != null &&
    typeof o.resources.cpu_percent === 'number' &&
    o.revenue != null &&
    typeof o.revenue.last_24h === 'number' &&
    o.security != null
  );
}

/** Instant paint when there is no cache yet — zeros, not a blocking skeleton. */
export function createEmptyDashboardData(): DashboardData {
  return {
    dashboard_partial: true,
    pipeline: {
      total_products: 0,
      active_products: 0,
      completed_products: 0,
      storefront_visible_products: null,
      failed_products: 0,
      pending_tasks: 0,
      running_tasks: 0,
      timed_out_tasks: 0,
      state_distribution: {},
      failed_alerts: [],
    },
    resources: { cpu_percent: 0, memory_percent: 0, disk_percent: 0 },
    revenue: { last_24h: 0, last_7d: 0, last_30d: 0 },
    security: { status: 'healthy', failed_logins_15min: 0 },
    agent_metrics: {},
    director_status: {
      report_count: 0,
      last_report_time: null,
      pending_decisions: 0,
      status: 'unknown',
    },
    escalation_summary: {
      total_all_time: 0,
      recent_1h: 0,
      by_agent: {},
      recent_events: [],
    },
  };
}

export function readAdminMetricsCache(): DashboardData | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(ADMIN_METRICS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { data?: unknown };
    if (!parsed || !isCachedMetricsPayload(parsed.data)) return null;
    return hydrateDashboardFromPipelineCache(parsed.data as DashboardData);
  } catch {
    return null;
  }
}

/** First paint: admin metrics cache, else pipeline catalog summary, else empty shell. */
export function bootDashboardData(): DashboardData {
  const cached = readAdminMetricsCache();
  if (cached) return cached;
  return hydrateDashboardFromPipelineCache(createEmptyDashboardData());
}

export function writeAdminMetricsCache(data: DashboardData): void {
  try {
    localStorage.setItem(ADMIN_METRICS_CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
  } catch {
    /* quota / private mode */
  }
}

/** Persist SSE / ad-hoc payloads only when they match the dashboard shape. */
export function writeAdminMetricsCacheIfValid(data: unknown): void {
  if (isCachedMetricsPayload(data)) {
    writeAdminMetricsCache(data);
  }
}

function maxCount(a: number | undefined, b: number | undefined): number {
  return Math.max(a ?? 0, b ?? 0);
}

/** Merge quick dashboard — never regress counts to zero when cache already has totals. */
export function mergeDashboardQuick(prev: DashboardData, quick: DashboardData): DashboardData {
  const storefront =
    quick.pipeline.storefront_visible_products ?? prev.pipeline.storefront_visible_products;
  const qp = quick.pipeline;
  const pp = prev.pipeline;
  return {
    ...quick,
    dashboard_partial: true,
    pipeline: {
      ...qp,
      total_products: maxCount(qp.total_products, pp.total_products),
      active_products: maxCount(qp.active_products, pp.active_products),
      completed_products: maxCount(qp.completed_products, pp.completed_products),
      failed_products: maxCount(qp.failed_products, pp.failed_products),
      pending_tasks: maxCount(qp.pending_tasks, pp.pending_tasks),
      running_tasks: maxCount(qp.running_tasks, pp.running_tasks),
      timed_out_tasks: maxCount(qp.timed_out_tasks, pp.timed_out_tasks),
      storefront_visible_products: storefront,
      state_distribution:
        Object.keys(qp.state_distribution ?? {}).length > 0
          ? qp.state_distribution
          : pp.state_distribution,
      failed_alerts: (qp.failed_alerts?.length ?? 0) > 0 ? qp.failed_alerts : pp.failed_alerts,
    },
  };
}

/** True when pipeline totals are authoritative (not the zero placeholder before API load). */
export function isPipelineMetricsReady(data: DashboardData): boolean {
  if (data.dashboard_build_degraded) return true;
  if (!data.dashboard_partial) return true;
  const p = data.pipeline;
  if ((p?.total_products ?? 0) > 0) return true;
  if ((p?.running_tasks ?? 0) + (p?.pending_tasks ?? 0) > 0) return true;
  const r = data.resources;
  if ((r?.memory_percent ?? 0) > 0 || (r?.cpu_percent ?? 0) > 0) return true;
  return false;
}

/** Public vitrine count only — must not mark the dashboard as fully loaded. */
export function applyPublicStorefrontCount(
  prev: DashboardData,
  vitrine: number,
): DashboardData {
  return {
    ...prev,
    pipeline: { ...prev.pipeline, storefront_visible_products: vitrine },
  };
}
