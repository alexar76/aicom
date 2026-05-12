import api from '@/lib/api';

/** Per-mode retries (transient 502 / proxy / worker busy / cold backend). */
export const PIPELINE_CATALOG_ATTEMPTS_LIGHT = 10;
export const PIPELINE_CATALOG_ATTEMPTS_FULL = 8;

export function pipelineCatalogBackoffMs(attempt: number): number {
  return Math.min(20_000, 500 * 2 ** attempt);
}

export async function fetchPipelineCatalogPageSingleMode(
  limit: number,
  offset: number,
  sort: 'newest' | 'shipped_first',
  light: boolean,
): Promise<Awaited<ReturnType<typeof api.getPipelineProducts>>> {
  const max = light ? PIPELINE_CATALOG_ATTEMPTS_LIGHT : PIPELINE_CATALOG_ATTEMPTS_FULL;
  let last: unknown;
  for (let i = 0; i < max; i++) {
    try {
      return await api.getPipelineProducts(limit, offset, sort, light);
    } catch (e) {
      last = e;
      if (i < max - 1) {
        await new Promise((r) => setTimeout(r, pipelineCatalogBackoffMs(i)));
      }
    }
  }
  if (last instanceof Error) throw last;
  throw new Error(String(last));
}

/**
 * Loads pipeline catalog: tries fast `light` mode first, then full hydration like Pipeline Monitor.
 */
export async function fetchPipelineCatalogResilient(
  limit: number,
  offset: number,
  sort: 'newest' | 'shipped_first',
): Promise<Awaited<ReturnType<typeof api.getPipelineProducts>>> {
  try {
    return await fetchPipelineCatalogPageSingleMode(limit, offset, sort, true);
  } catch {
    return await fetchPipelineCatalogPageSingleMode(limit, offset, sort, false);
  }
}

/** Matches admin API `le=2000` — largest page the backend allows per request. */
export const PIPELINE_CATALOG_MAX_PAGE = 2000;

/**
 * Streams the full pipeline catalog in pages (no artificial client cap).
 * Calls `onPage` after each successful page so the UI can render incrementally.
 */
export async function fetchPipelineCatalogAllPages(
  sort: 'newest' | 'shipped_first' = 'shipped_first',
  opts?: {
    onPage?: (info: { batch: any[]; loaded: number; total: number | null }) => void;
    signal?: AbortSignal;
  },
): Promise<void> {
  let offset = 0;
  let total: number | null = null;

  for (;;) {
    if (opts?.signal?.aborted) return;
    const data = await fetchPipelineCatalogResilient(PIPELINE_CATALOG_MAX_PAGE, offset, sort);
    if (opts?.signal?.aborted) return;
    const batch = data.products || [];
    if (typeof data.total === 'number') {
      total = data.total;
    }
    offset += batch.length;
    opts?.onPage?.({ batch, loaded: offset, total });

    if (batch.length === 0) return;
    if (total != null && offset >= total) return;
    if (batch.length < PIPELINE_CATALOG_MAX_PAGE) return;
  }
}
