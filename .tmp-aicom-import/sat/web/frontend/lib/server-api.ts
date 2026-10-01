import type { Product } from '@/lib/api';
import { promises as fs } from 'node:fs';
import path from 'node:path';

function apiBase(): string {
  return (
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_INTERNAL_API_URL ||
    'http://127.0.0.1:8081'
  ).replace(/\/$/, '');
}

async function readJsonFile<T>(absPath: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(absPath, 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

type DataSourceMode = 'api_first' | 'local_first';

function isBuildPhase(): boolean {
  return process.env.NEXT_PHASE === 'phase-production-build';
}

function dataSourceMode(): DataSourceMode {
  const raw = (process.env.AIFACTORY_SERVER_API_SOURCE || '').trim().toLowerCase();
  if (raw === 'local' || raw === 'local_first') return 'local_first';
  if (raw === 'api' || raw === 'api_first') return 'api_first';
  // Safe default: during `next build` avoid hard dependency on loopback API.
  return isBuildPhase() ? 'local_first' : 'api_first';
}

async function detectDataRoot(): Promise<string | null> {
  const candidates = [
    process.env.AIFACTORY_DATA_ROOT,
    '/app/data',
    path.resolve(process.cwd(), '../../data'),
    path.resolve(process.cwd(), '../data'),
    path.resolve(process.cwd(), 'data'),
  ].filter(Boolean) as string[];

  for (const p of candidates) {
    try {
      await fs.access(path.join(p, 'state'));
      return p;
    } catch {
      // try next
    }
  }
  return null;
}

function mapLocalProduct(pid: string, raw: Record<string, any>, marketingDoc?: Record<string, any>): Product {
  const marketing = (marketingDoc?.marketing || marketingDoc || {}) as Record<string, any>;
  const localName =
    marketing.product_name ||
    raw.name ||
    raw?.spec?.product_name ||
    raw.idea;
  const localDesc =
    marketing.selling_description ||
    marketing.short_description ||
    raw.selling_description ||
    raw.idea ||
    '';
  const category = marketing.category || raw.category || raw?.metadata?.category;
  const tags = marketing.tags || raw.tags || raw?.metadata?.tags;
  return {
    id: pid,
    name: localName,
    idea: String(raw.idea || ''),
    state: String(raw.state || ''),
    created_at: Number(raw.created_at || 0),
    category: category ? String(category) : undefined,
    tags: Array.isArray(tags) ? tags.map((x) => String(x)) : undefined,
    selling_description: String(localDesc || ''),
    delivery_profile: raw.delivery_profile != null ? String(raw.delivery_profile) : undefined,
  };
}

async function loadLocalProducts(): Promise<Record<string, any> | null> {
  const dataRoot = await detectDataRoot();
  if (!dataRoot) return null;
  const pipeline = await readJsonFile<{ products?: Record<string, any> }>(
    path.join(dataRoot, 'state', 'pipeline.json'),
  );
  return pipeline?.products || null;
}

async function loadLocalMarketing(productId: string): Promise<Record<string, any> | null> {
  const dataRoot = await detectDataRoot();
  if (!dataRoot) return null;
  return readJsonFile<Record<string, any>>(
    path.join(dataRoot, 'state', productId, 'marketing_content.json'),
  );
}

async function readSpecDeliveryProfile(productId: string): Promise<string | null> {
  const dataRoot = await detectDataRoot();
  if (!dataRoot) return null;
  const doc = await readJsonFile<{ specification?: { delivery_profile?: string } }>(
    path.join(dataRoot, 'specs', productId, 'specification.json'),
  );
  const v = doc?.specification?.delivery_profile;
  return v != null ? String(v) : null;
}

/** Mirrors backend agents.product_profile.normalize_delivery_profile enough for storefront filtering. */
function normalizedListingDeliveryProfile(
  productRaw: Record<string, any>,
  specDeliveryProfile: string | null,
): 'marketing_landing' | 'full_software' | null {
  const raw = String(specDeliveryProfile ?? productRaw.delivery_profile ?? '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')
    .replace(/ /g, '_');
  if (!raw) return null;
  if (
    raw === 'marketing_landing' ||
    raw === 'marketing' ||
    raw === 'landing_only' ||
    raw === 'promo_only' ||
    raw === 'brochure'
  ) {
    return 'marketing_landing';
  }
  return 'full_software';
}

export async function getProductForMetadata(id: string): Promise<Product | null> {
  const fromApi = async (): Promise<Product | null> => {
    const res = await fetch(`${apiBase()}/api/products/${encodeURIComponent(id)}`, {
      next: { revalidate: 120 },
    });
    if (!res.ok) return null;
    return res.json() as Promise<Product>;
  };

  const fromLocal = async (): Promise<Product | null> => {
    const products = await loadLocalProducts();
    if (!products || !products[id]) return null;
    const marketing = await loadLocalMarketing(id);
    return mapLocalProduct(id, products[id], marketing || undefined);
  };

  const mode = dataSourceMode();
  if (mode === 'api_first') {
    try {
      const p = await fromApi();
      if (p) return p;
    } catch {
      // fall through to local
    }
    return fromLocal();
  }
  const local = await fromLocal();
  if (local) return local;
  try {
    return await fromApi();
  } catch {
    return null;
  }
}

export async function getProductsByCategory(category: string): Promise<Product[]> {
  const fromLocal = async (): Promise<Product[]> => {
    const products = await loadLocalProducts();
    if (!products) return [];
    const out: Product[] = [];
    for (const [pid, raw] of Object.entries(products)) {
      const state = String((raw as Record<string, any>).state || '').toUpperCase();
      if (state !== 'COMPLETED' && state !== 'DEPLOYED_PRODUCTION') continue;
      const specDp = await readSpecDeliveryProfile(pid);
      const ndp = normalizedListingDeliveryProfile(raw as Record<string, any>, specDp);
      const isLanding = ndp === 'marketing_landing';

      if (category === 'landings') {
        if (!isLanding) continue;
      } else {
        if (isLanding) continue;
      }

      const marketing = await loadLocalMarketing(pid);
      const mapped = mapLocalProduct(pid, raw as Record<string, any>, marketing || undefined);
      if (category === 'landings') {
        mapped.delivery_profile = 'marketing_landing';
        out.push(mapped);
        continue;
      }
      const cat = String(mapped.category || 'uncategorized');
      if (cat === category) out.push(mapped);
    }
    return out;
  };

  const fromApi = async (): Promise<Product[]> => {
    const q = encodeURIComponent(category);
    const res = await fetch(`${apiBase()}/api/products?category=${q}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.products || [];
  };

  const mode = dataSourceMode();
  if (mode === 'api_first') {
    try {
      const apiProducts = await fromApi();
      if (apiProducts.length > 0) return apiProducts;
    } catch {
      // fall through to local
    }
    return fromLocal();
  }
  const local = await fromLocal();
  if (local.length > 0) return local;
  try {
    return await fromApi();
  } catch {
    return local;
  }
}

// ---------------------------------------------------------------------------
// Public build replay (shareable `/build/{id}` permalink + `/builds` gallery)
// ---------------------------------------------------------------------------

export type BuildStage = {
  agent: string;
  label: string;
  emoji: string;
  blurb: string;
  state: string | null;
  status: 'completed' | 'running' | 'failed' | 'pending' | string;
  is_gate: boolean;
  had_error: boolean;
  retry_count: number;
  started_at: number | null;
  completed_at: number | null;
  created_at: number | null;
  duration_sec: number | null;
  highlights: Record<string, string | number | boolean>;
};

export type BuildSummary = {
  id: string;
  title: string;
  idea: string;
  state: string | null;
  category: string | null;
  shipped: boolean;
  created_at: number | null;
  updated_at: number | null;
  stage_count: number;
  completed_stage_count: number;
  total_build_seconds: number | null;
  repair_rounds: number;
  product_url: string;
};

export type BuildReplay = { build: BuildSummary; stages: BuildStage[] };

export type BuildCard = {
  id: string;
  title: string;
  state: string | null;
  category: string | null;
  shipped: boolean;
  created_at: number | null;
  stage_count: number;
  replay_url: string;
  product_url: string;
};

export async function getBuildReplay(id: string): Promise<BuildReplay | null> {
  try {
    const res = await fetch(`${apiBase()}/api/public/build/${encodeURIComponent(id)}`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return null;
    return (await res.json()) as BuildReplay;
  } catch {
    return null;
  }
}

export async function listBuilds(limit = 24): Promise<BuildCard[]> {
  try {
    const res = await fetch(`${apiBase()}/api/public/builds?limit=${encodeURIComponent(String(limit))}`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data?.builds as BuildCard[]) || [];
  } catch {
    return [];
  }
}

export type FactoryAgentRow = {
  agent_id: string;
  name: string;
  product_id: string;
  sdk: string;
  version: string;
  public_url: string;
  status: string;
  verified: boolean;
  age_sec: number;
  capabilities_used: string[];
  invokes_total: number;
  spend_usd_total: number;
};

export type FactoryAgentsRoster = {
  agents: FactoryAgentRow[];
  summary: {
    agents_total: number;
    agents_live: number;
    invokes_total: number;
    spend_usd_total: number;
    sdks?: Record<string, number>;
    capabilities?: Record<string, number>;
  };
};

export async function listFactoryAgents(): Promise<FactoryAgentsRoster> {
  const empty: FactoryAgentsRoster = {
    agents: [],
    summary: { agents_total: 0, agents_live: 0, invokes_total: 0, spend_usd_total: 0 },
  };
  try {
    const res = await fetch(`${apiBase()}/api/agents`, { next: { revalidate: 30 } });
    if (!res.ok) return empty;
    const data = await res.json();
    const agents = Array.isArray(data?.agents) ? data.agents : [];
    const summary = data?.summary && typeof data.summary === 'object' ? data.summary : empty.summary;
    return {
      agents: agents.map((a: Record<string, unknown>) => {
        const stats = (a.stats as Record<string, unknown>) || {};
        return {
          agent_id: String(a.agent_id || ''),
          name: String(a.name || a.agent_id || ''),
          product_id: String(a.product_id || ''),
          sdk: String(a.sdk || ''),
          version: String(a.version || ''),
          public_url: String(a.public_url || ''),
          status: String(a.status || 'offline'),
          verified: Boolean(a.verified),
          age_sec: Number(a.age_sec || 0),
          capabilities_used: Array.isArray(a.capabilities_used)
            ? a.capabilities_used.map((c) => String(c))
            : [],
          invokes_total: Number(stats.invokes_total || 0),
          spend_usd_total: Number(stats.spend_usd_total || 0),
        };
      }),
      summary: {
        agents_total: Number(summary.agents_total || agents.length),
        agents_live: Number(summary.agents_live || 0),
        invokes_total: Number(summary.invokes_total || 0),
        spend_usd_total: Number(summary.spend_usd_total || 0),
        sdks: summary.sdks as Record<string, number> | undefined,
        capabilities: summary.capabilities as Record<string, number> | undefined,
      },
    };
  } catch {
    return empty;
  }
}
