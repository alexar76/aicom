/**
 * Warm dashboard metrics before / as Admin shell mounts (first paint uses localStorage or zeros).
 */

import { writeFactoryFloorCache, type FactoryFloorPayload } from '@/lib/factoryFloorCache';
import {
  loadAdminDashboardFull,
  loadAdminDashboardLayers,
} from '@/lib/loadAdminDashboardLayers';

let inflight: Promise<void> | null = null;

export function prefetchAdminDashboard(): void {
  if (typeof window === 'undefined') return;
  if (inflight) return;
  inflight = (async () => {
    await loadAdminDashboardLayers();
    try {
      const full = await loadAdminDashboardFull();
      if (full?.factory_floor) {
        writeFactoryFloorCache(full.factory_floor as FactoryFloorPayload);
      }
    } catch {
      /* quick or prior cache remains */
    }
  })().finally(() => {
    inflight = null;
  });
}
