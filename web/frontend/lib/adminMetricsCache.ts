/**
 * Shared localStorage snapshot for Admin dashboard + Live Monitor metrics.
 * Same payload shape as GET /api/admin/dashboard (full) and SSE metrics stream.
 */

import type { DashboardData } from '@/lib/api';

export const ADMIN_METRICS_CACHE_KEY = 'aicom_admin_dashboard_swr_v4';

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
    return parsed.data;
  } catch {
    return null;
  }
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

/** Merge quick dashboard — do not keep stale storefront counts from old cache. */
export function mergeDashboardQuick(prev: DashboardData, quick: DashboardData): DashboardData {
  const storefront =
    quick.pipeline.storefront_visible_products ?? prev.pipeline.storefront_visible_products;
  return {
    ...quick,
    dashboard_partial: true,
    pipeline: {
      ...quick.pipeline,
      storefront_visible_products: storefront,
    },
  };
}

/** True when pipeline totals are authoritative (not the zero placeholder before API load). */
export function isPipelineMetricsReady(data: DashboardData): boolean {
  if (data.dashboard_build_degraded) return true;
  if (!data.dashboard_partial) return true;
  return (data.pipeline?.total_products ?? 0) > 0;
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
