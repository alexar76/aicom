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
  onAttempt?: (info: { attempt: number; maxAttempts: number }) => void,
): Promise<Awaited<ReturnType<typeof api.getPipelineProducts>>> {
  const max = light ? PIPELINE_CATALOG_ATTEMPTS_LIGHT : PIPELINE_CATALOG_ATTEMPTS_FULL;
  let last: unknown;
  for (let i = 0; i < max; i++) {
    onAttempt?.({ attempt: i, maxAttempts: max });
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
 *
 * @param opts.startOffset — skip earlier products (for "load more" after initial slice).
 * @param opts.maxPages — stop after N API pages (e.g. `1` for lazy first paint, then append).
 */
export async function fetchPipelineCatalogAllPages(
  sort: 'newest' | 'shipped_first' = 'shipped_first',
  opts?: {
    onPage?: (info: { batch: any[]; loaded: number; total: number | null }) => void;
    signal?: AbortSignal;
    startOffset?: number;
    maxPages?: number;
  },
): Promise<void> {
  let offset = Math.max(0, opts?.startOffset ?? 0);
  let total: number | null = null;
  let pagesDone = 0;

  for (;;) {
    if (opts?.signal?.aborted) return;
    const data = await fetchPipelineCatalogResilient(PIPELINE_CATALOG_MAX_PAGE, offset, sort);
    if (opts?.signal?.aborted) return;
    const batch = data.products || [];
    if (typeof data.total === 'number') {
      total = data.total;
    }
    offset += batch.length;
    pagesDone += 1;
    opts?.onPage?.({ batch, loaded: offset, total });

    if (opts?.maxPages != null && pagesDone >= opts.maxPages) return;

    if (batch.length === 0) return;
    if (total != null && offset >= total) return;
    if (batch.length < PIPELINE_CATALOG_MAX_PAGE) return;
  }
}
