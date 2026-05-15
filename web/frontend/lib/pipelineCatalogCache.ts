/**
 * localStorage snapshot for Admin Pipeline Monitor: last successful catalog slice + summary totals.
 * Stale tail may be shown briefly while chunked network refresh runs (same sort key).
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

const CACHE_VERSION = 1 as const;

type StoredEnvelope = {
  v: typeof CACHE_VERSION;
  ts: number;
  sort: 'newest' | 'shipped_first';
  total: number;
  products: unknown[];
  catalog_summary: PipelineCatalogSummaryCached | null;
};

export function pipelineCatalogCacheKey(sort: 'newest' | 'shipped_first'): string {
  return `aicom_pipeline_catalog_v${CACHE_VERSION}_${sort}`;
}

function isSort(x: unknown): x is 'newest' | 'shipped_first' {
  return x === 'newest' || x === 'shipped_first';
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
  try {
    const raw = localStorage.getItem(pipelineCatalogCacheKey(sort));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredEnvelope>;
    if (!parsed || parsed.v !== CACHE_VERSION || !isSort(parsed.sort)) return null;
    if (parsed.sort !== sort) return null;
    const total = typeof parsed.total === 'number' && Number.isFinite(parsed.total) ? parsed.total : NaN;
    if (!(total >= 0)) return null;
    if (!Array.isArray(parsed.products)) return null;
    if (parsed.products.length === 0 && total > 0) return null;
    const cs = parsed.catalog_summary;
    const catalog_summary: PipelineCatalogSummaryCached | null =
      cs &&
      typeof cs === 'object' &&
      typeof cs.total_products === 'number' &&
      typeof cs.shipped_products === 'number' &&
      typeof cs.failed_products === 'number'
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

/** Avoid huge JSON — same order of magnitude as the in-memory catalog list. */
const MAX_PRODUCTS_TO_PERSIST = 3000;

function tryPersist(sort: 'newest' | 'shipped_first', body: Omit<StoredEnvelope, 'v'>): boolean {
  const payload: StoredEnvelope = { v: CACHE_VERSION, ...body };
  const key = pipelineCatalogCacheKey(sort);
  try {
    localStorage.setItem(key, JSON.stringify(payload));
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

  let products = args.products;
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
