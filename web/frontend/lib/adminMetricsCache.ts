/**
 * Shared localStorage snapshot for Admin dashboard + Live Monitor metrics.
 * Same payload shape as GET /api/admin/dashboard (full) and SSE metrics stream.
 */

import type { DashboardData } from '@/lib/api';

export const ADMIN_METRICS_CACHE_KEY = 'aicom_admin_dashboard_swr_v1';

function isCachedMetricsPayload(x: unknown): x is DashboardData {
  if (!x || typeof x !== 'object') return false;
  const o = x as DashboardData;
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
