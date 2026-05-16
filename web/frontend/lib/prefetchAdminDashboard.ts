/**
 * Warm dashboard metrics before / as Admin shell mounts (first paint uses localStorage or zeros).
 */

import api from '@/lib/api';
import {
  mergeDashboardQuick,
  readAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';

let inflight: Promise<void> | null = null;

export function prefetchAdminDashboard(): void {
  if (typeof window === 'undefined') return;
  if (inflight) return;
  inflight = (async () => {
    try {
      const quick = await api.getDashboard(true);
      const prev = readAdminMetricsCache();
      if (prev) {
        writeAdminMetricsCache(mergeDashboardQuick(prev, quick));
      } else {
        writeAdminMetricsCache({ ...quick, dashboard_partial: true });
      }
    } catch {
      /* ignore */
    }
    try {
      const full = await api.getDashboard(false);
      writeAdminMetricsCache(full);
    } catch {
      /* quick or prior cache remains */
    }
  })().finally(() => {
    inflight = null;
  });
}
