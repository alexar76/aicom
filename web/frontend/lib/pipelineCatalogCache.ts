/**
 * localStorage snapshot for Admin Pipeline Monitor: catalog rows + summary totals.
 * v2 stores slim rows (smaller JSON.parse, less main-thread blocking on tab open).
 */

export type PipelineCatalogSummaryCached = {
  total_products: number;
  shipped_products: number;
  failed_products: number;
  storefront_listable_products: number | null;
  light?: boolean;
  sort: string;
  sort_note?: string;
};

/** Bump when on-disk shape changes (e.g. slim rows). */
const CACHE_VERSION = 2 as const;
const LEGACY_CACHE_VERSION = 1 as const;

type StoredEnvelope = {
  v: typeof CACHE_VERSION | typeof LEGACY_CACHE_VERSION;
  ts: number;
  sort: 'newest' | 'shipped_first';
  total: number;
  products: unknown[];
  catalog_summary: PipelineCatalogSummaryCached | null;
};

export function pipelineCatalogCacheKey(sort: 'newest' | 'shipped_first'): string {
  return `aicom_pipeline_catalog_v${CACHE_VERSION}_${sort}`;
}

/** Tiny JSON (first 2 rows + totals) for instant paint when the full cache blob is slow or missing. */
const PEEK_VERSION = 1 as const;

export function pipelineCatalogPeekKey(sort: 'newest' | 'shipped_first'): string {
  return `aicom_pipeline_monitor_peek_v${PEEK_VERSION}_${sort}`;
}

type PeekEnvelope = {
  v: typeof PEEK_VERSION;
  ts: number;
  sort: 'newest' | 'shipped_first';
  total: number;
  products: unknown[];
  catalog_summary: PipelineCatalogSummaryCached | null;
};

export function readPipelineCatalogPeek(sort: 'newest' | 'shipped_first'): {
  products: any[];
  total: number;
  catalog_summary: PipelineCatalogSummaryCached | null;
  savedAt: number;
} | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(pipelineCatalogPeekKey(sort));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PeekEnvelope>;
    if (!parsed || parsed.v !== PEEK_VERSION || !isSort(parsed.sort) || parsed.sort !== sort) return null;
    const total = typeof parsed.total === 'number' && Number.isFinite(parsed.total) ? parsed.total : NaN;
    if (!(total >= 0)) return null;
    if (!Array.isArray(parsed.products) || parsed.products.length === 0) return null;
    const cs = parsed.catalog_summary;
    const catalog_summary: PipelineCatalogSummaryCached | null =
      cs &&
      typeof cs === 'object' &&
      typeof (cs as PipelineCatalogSummaryCached).total_products === 'number' &&
      typeof (cs as PipelineCatalogSummaryCached).shipped_products === 'number' &&
      typeof (cs as PipelineCatalogSummaryCached).failed_products === 'number'
        ? (cs as PipelineCatalogSummaryCached)
        : null;
    const savedAt = typeof parsed.ts === 'number' ? parsed.ts : 0;
    return {
      products: parsed.products as any[],
      total,
      catalog_summary,
      savedAt,
    };
  } catch {
    return null;
  }
}

function writePipelineCatalogPeek(
  sort: 'newest' | 'shipped_first',
  slimProducts: Record<string, unknown>[],
  total: number,
  catalog_summary: PipelineCatalogSummaryCached | null,
): void {
  if (typeof window === 'undefined') return;
  try {
    const payload: PeekEnvelope = {
      v: PEEK_VERSION,
      ts: Date.now(),
      sort,
      total,
      catalog_summary,
      products: slimProducts.slice(0, 2),
    };
    localStorage.setItem(pipelineCatalogPeekKey(sort), JSON.stringify(payload));
  } catch {
    /* quota */
  }
}

/** Persist only the tiny peek slice immediately after the first live API batch (not debounced). */
export function persistPipelineCatalogPeekFromProducts(
  sort: 'newest' | 'shipped_first',
  products: any[],
  total: number,
  catalog_summary: PipelineCatalogSummaryCached | null,
): void {
  writePipelineCatalogPeek(sort, products.map(slimPipelineCatalogProduct), total, catalog_summary);
}

/** v1 keys still used by older clients — overwritten on next successful save. */
function legacyPipelineCatalogCacheKey(sort: 'newest' | 'shipped_first'): string {
  return `aicom_pipeline_catalog_v${LEGACY_CACHE_VERSION}_${sort}`;
}

function isSort(x: unknown): x is 'newest' | 'shipped_first' {
  return x === 'newest' || x === 'shipped_first';
}

const TASK_JSON_SOFT_CAP = 14_000;

function slimTaskForCache(t: unknown): Record<string, unknown> {
  if (!t || typeof t !== 'object') return {};
  const src = t as Record<string, unknown>;
  const keys = [
    'id',
    'agent_type',
    'status',
    'state',
    'created_at',
    'started_at',
    'completed_at',
    'ended_at',
    'updated_at',
    'error',
    'metrics',
    'timeout_sec',
    'priority',
    'retry_count',
    'max_retries',
  ] as const;
  const o: Record<string, unknown> = {};
  for (const k of keys) {
    if (src[k] !== undefined) o[k] = src[k];
  }
  for (const blobKey of ['input_data', 'output_data'] as const) {
    const v = src[blobKey];
    if (v == null) continue;
    try {
      const s = JSON.stringify(v);
      if (s.length <= TASK_JSON_SOFT_CAP) {
        o[blobKey] = v;
      } else {
        o[blobKey] = { _pipeline_cache_truncated: true, _approx_chars: s.length };
      }
    } catch {
      /* skip */
    }
  }
  return o;
}

function slimSpec(spec: unknown): Record<string, unknown> | undefined {
  if (!spec || typeof spec !== 'object') return undefined;
  const s = spec as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  if (typeof s.product_name === 'string') out.product_name = s.product_name;
  if (typeof s.description === 'string') out.description = s.description;
  if (typeof s.delivery_profile === 'string') out.delivery_profile = s.delivery_profile;
  const inner = s.specification;
  if (inner && typeof inner === 'object') {
    const inn = inner as Record<string, unknown>;
    if (typeof inn.delivery_profile === 'string') {
      out.specification = { delivery_profile: inn.delivery_profile };
    }
  }
  return Object.keys(out).length ? out : undefined;
}

/**
 * Strip heavy / redundant fields before localStorage — keeps cards + filters + panels usable,
 * full task payloads refetch with the next API slice.
 */
export function slimPipelineCatalogProduct(p: unknown): Record<string, unknown> {
  if (!p || typeof p !== 'object') return {};
  const src = p as Record<string, unknown>;
  if (src.id == null) return { ...src };

  const o: Record<string, unknown> = {
    id: src.id,
    state: src.state,
    created_at: src.created_at,
  };
  for (const k of ['idea', 'category', 'failure_reason', 'last_error', 'delivery_profile'] as const) {
    const v = src[k];
    if (typeof v === 'string') o[k] = v;
  }

  if (typeof src.production_mode === 'boolean') o.production_mode = src.production_mode;
  if (typeof src.quality_repair_round === 'number') o.quality_repair_round = src.quality_repair_round;

  if (Array.isArray(src.tags)) o.tags = src.tags.slice(0, 64);
  if (Array.isArray(src.failed_task_errors)) {
    o.failed_task_errors = src.failed_task_errors
      .slice(0, 24)
      .map((x: unknown) => (typeof x === 'string' ? x.slice(0, 800) : String(x).slice(0, 800)));
  }

  const specSlim = slimSpec(src.spec);
  if (specSlim) o.spec = specSlim;

  if (src.economics && typeof src.economics === 'object') o.economics = src.economics;
  if (src.pulse && typeof src.pulse === 'object') o.pulse = src.pulse;

  if (typeof src.storefront_visible === 'boolean') o.storefront_visible = src.storefront_visible;
  if (Array.isArray(src.storefront_gate_reasons)) {
    o.storefront_gate_reasons = src.storefront_gate_reasons.slice(0, 48);
  }
  if (src.storefront_followup && typeof src.storefront_followup === 'object') {
    o.storefront_followup = src.storefront_followup;
  }
  if (src.storefront_marketing_copy && typeof src.storefront_marketing_copy === 'object') {
    o.storefront_marketing_copy = src.storefront_marketing_copy;
  }
  if (typeof src.storefront_admin_price_usdt === 'number') {
    o.storefront_admin_price_usdt = src.storefront_admin_price_usdt;
  }
  if (typeof src.storefront_effective_price_usdt === 'number') {
    o.storefront_effective_price_usdt = src.storefront_effective_price_usdt;
  }
  if (typeof src.storefront_price_tier === 'string') o.storefront_price_tier = src.storefront_price_tier;

  if (src.task_counts && typeof src.task_counts === 'object') o.task_counts = src.task_counts;
  if (Array.isArray(src.tasks)) {
    o.tasks = src.tasks.map(slimTaskForCache);
  }

  return o;
}

function parseEnvelope(raw: string): Partial<StoredEnvelope> | null {
  try {
    const parsed = JSON.parse(raw) as Partial<StoredEnvelope>;
    if (!parsed || (parsed.v !== CACHE_VERSION && parsed.v !== LEGACY_CACHE_VERSION)) return null;
    if (!isSort(parsed.sort)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function readPipelineCatalogCache(
  sort: 'newest' | 'shipped_first',
): {
  products: any[];
  total: number;
  catalog_summary: PipelineCatalogSummaryCached | null;
  savedAt: number;
} | null {
  if (typeof window === 'undefined') return null;

  type Hit = {
    products: any[];
    total: number;
    catalog_summary: PipelineCatalogSummaryCached | null;
    savedAt: number;
  };

  const tryKey = (key: string): Hit | null => {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = parseEnvelope(raw);
    if (!parsed || parsed.sort !== sort) return null;
    const total = typeof parsed.total === 'number' && Number.isFinite(parsed.total) ? parsed.total : NaN;
    if (!(total >= 0)) return null;
    if (!Array.isArray(parsed.products)) return null;
    if (parsed.products.length === 0 && total > 0) return null;
    const cs = parsed.catalog_summary;
    const catalog_summary: PipelineCatalogSummaryCached | null =
      cs &&
      typeof cs === 'object' &&
      typeof (cs as PipelineCatalogSummaryCached).total_products === 'number' &&
      typeof (cs as PipelineCatalogSummaryCached).shipped_products === 'number' &&
      typeof (cs as PipelineCatalogSummaryCached).failed_products === 'number'
        ? (cs as PipelineCatalogSummaryCached)
        : null;
    const savedAt = typeof parsed.ts === 'number' ? parsed.ts : 0;
    return {
      products: parsed.products as any[],
      total,
      catalog_summary,
      savedAt,
    };
  };

  return tryKey(pipelineCatalogCacheKey(sort)) ?? tryKey(legacyPipelineCatalogCacheKey(sort));
}

/** Avoid huge JSON — slim rows allow more headroom. */
const MAX_PRODUCTS_TO_PERSIST = 4000;

function tryPersist(sort: 'newest' | 'shipped_first', body: Omit<StoredEnvelope, 'v'>): boolean {
  const payload: StoredEnvelope = { v: CACHE_VERSION, ...body };
  const key = pipelineCatalogCacheKey(sort);
  try {
    localStorage.setItem(key, JSON.stringify(payload));
    try {
      localStorage.removeItem(legacyPipelineCatalogCacheKey(sort));
    } catch {
      /* ignore */
    }
    return true;
  } catch {
    return false;
  }
}

export function writePipelineCatalogCache(args: {
  sort: 'newest' | 'shipped_first';
  total: number;
  products: any[];
  catalog_summary: PipelineCatalogSummaryCached | null;
}): void {
  if (typeof window === 'undefined') return;

  let products = args.products.map(slimPipelineCatalogProduct);
  writePipelineCatalogPeek(args.sort, products, args.total, args.catalog_summary);
  const cap = MAX_PRODUCTS_TO_PERSIST;
  if (products.length > cap) {
    products = products.slice(0, cap);
  }

  let body: Omit<StoredEnvelope, 'v'> = {
    ts: Date.now(),
    sort: args.sort,
    total: args.total,
    products,
    catalog_summary: args.catalog_summary,
  };

  let attempts = 0;
  while (attempts < 8) {
    if (tryPersist(args.sort, body)) return;
    attempts += 1;
    const shrink = Math.max(48, Math.floor(body.products.length * 0.55));
    body = {
      ...body,
      ts: Date.now(),
      products: body.products.slice(0, shrink),
    };
    if (body.products.length <= 24) break;
  }
}
