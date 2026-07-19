/**
 * Factory Floor snapshot — instant paint from dashboard cache, then lazy live refresh.
 */

import {
  createEmptyDashboardData,
  readAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';

export type FactoryFloorNode = {
  id: string;
  label: string;
  status: string;
  prompt_line?: string;
  provider?: string;
  model?: string;
  latency_ms?: number | null;
  cost_usd?: number;
  product_id?: string | null;
  circuit_tripped?: boolean;
};

export type AiMarketFloorEvent = {
  type?: string;
  product_id?: string;
  capability_id?: string;
  price_usd?: number;
  latency_ms?: number;
  success?: boolean;
  time?: number;
};

export type FactoryFloorPayload = {
  nodes?: FactoryFloorNode[];
  edges?: Array<{ from: string; to: string; kind?: string }>;
  hot_edges?: Array<{ from: string; to: string; pulse_id?: string }>;
  running_count?: number;
  open_circuits?: string[];
  updated_at?: number;
  ai_market?: { events?: AiMarketFloorEvent[]; total_usd_1h?: number };
};

function isFactoryFloorPayload(x: unknown): x is FactoryFloorPayload {
  if (!x || typeof x !== 'object') return false;
  const nodes = (x as FactoryFloorPayload).nodes;
  return Array.isArray(nodes) && nodes.length > 0;
}

export function readFactoryFloorCache(): FactoryFloorPayload | null {
  const fromDash = readAdminMetricsCache()?.factory_floor;
  if (isFactoryFloorPayload(fromDash)) return fromDash;
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem('aicom_factory_floor_v1');
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { data?: unknown };
    return isFactoryFloorPayload(parsed.data) ? parsed.data : null;
  } catch {
    return null;
  }
}

export function writeFactoryFloorCache(floor: FactoryFloorPayload): void {
  if (!isFactoryFloorPayload(floor)) return;
  try {
    localStorage.setItem(
      'aicom_factory_floor_v1',
      JSON.stringify({ ts: Date.now(), data: floor }),
    );
  } catch {
    /* quota */
  }
  const prev = readAdminMetricsCache() ?? createEmptyDashboardData();
  writeAdminMetricsCache({ ...prev, factory_floor: floor });
}
