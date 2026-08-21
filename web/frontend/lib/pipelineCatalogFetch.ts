import api from '@/lib/api';

/** Per-mode retries (transient 502 / proxy / worker busy / cold backend). */
export const PIPELINE_CATALOG_ATTEMPTS_LIGHT = 10;
export const PIPELINE_CATALOG_ATTEMPTS_FULL = 8;
/** First catalog page (Pipeline Monitor): fail faster so the UI is not stuck ~30s on backoff. */
export const PIPELINE_CATALOG_FIRST_PAGE_ATTEMPTS_LIGHT = 8;
export const PIPELINE_CATALOG_FIRST_PAGE_BACKOFF_CAP_MS = 8000;

/** Per-attempt HTTP timeout (heavy catalog / slow proxy). Was 180s; raised for large DB + cold start. */
export const PIPELINE_CATALOG_CLIENT_TIMEOUT_MS = 300_000;

export type PipelineCatalogFetchOpts = {
  maxAttempts?: number;
  /** Upper bound for exponential backoff (ms). */
  backoffCapMs?: number;
  /** AbortSignal.timeout for each HTTP attempt (defaults to {@link PIPELINE_CATALOG_CLIENT_TIMEOUT_MS}). */
  clientTimeoutMs?: number;
};

/** Fired before each HTTP attempt; after a failure (before sleeping), includes `lastError` + `backoffMs`. */
export type PipelineCatalogAttemptInfo = {
  attempt: number;
  maxAttempts: number;
  lastError?: string;
  /** Present when waiting before the next attempt. */
  backoffMs?: number;
};

export function pipelineCatalogBackoffMs(attempt: number, capMs: number = 20_000): number {
  return Math.min(capMs, 500 * 2 ** attempt);
}

export async function fetchPipelineCatalogPageSingleMode(
  limit: number,
  offset: number,
  sort: 'newest' | 'shipped_first',
  light: boolean,
  onAttempt?: (info: PipelineCatalogAttemptInfo) => void,
  fetchOpts?: PipelineCatalogFetchOpts,
): Promise<Awaited<ReturnType<typeof api.getPipelineProducts>>> {
  const defaultMax = light ? PIPELINE_CATALOG_ATTEMPTS_LIGHT : PIPELINE_CATALOG_ATTEMPTS_FULL;
  const max = Math.max(1, Math.min(30, fetchOpts?.maxAttempts ?? defaultMax));
  const capMs = fetchOpts?.backoffCapMs ?? 20_000;
  const clientTimeoutMs = fetchOpts?.clientTimeoutMs ?? PIPELINE_CATALOG_CLIENT_TIMEOUT_MS;
  let last: unknown;
  for (let i = 0; i < max; i++) {
    onAttempt?.({ attempt: i, maxAttempts: max });
    try {
      return await api.getPipelineProducts(limit, offset, sort, light, clientTimeoutMs);
    } catch (e) {
      last = e;
      if (i < max - 1) {
        const backoffMs = pipelineCatalogBackoffMs(i, capMs);
        const lastError = e instanceof Error ? e.message : String(e);
        onAttempt?.({ attempt: i, maxAttempts: max, lastError, backoffMs });
        await new Promise((r) => setTimeout(r, backoffMs));
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
    return await fetchPipelineCatalogPageSingleMode(limit, offset, sort, true, undefined, undefined);
  } catch {
    return await fetchPipelineCatalogPageSingleMode(limit, offset, sort, false, undefined, undefined);
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
 * @param opts.pageSize — rows per request (default max page size 2000; use e.g. 2 for tiny batches).
 */
export async function fetchPipelineCatalogAllPages(
  sort: 'newest' | 'shipped_first' = 'shipped_first',
  opts?: {
    onPage?: (info: { batch: any[]; loaded: number; total: number | null }) => void;
    signal?: AbortSignal;
    startOffset?: number;
    maxPages?: number;
    pageSize?: number;
  },
): Promise<void> {
  const pageSize = Math.min(
    PIPELINE_CATALOG_MAX_PAGE,
    Math.max(1, Math.floor(opts?.pageSize ?? PIPELINE_CATALOG_MAX_PAGE)),
  );
  let offset = Math.max(0, opts?.startOffset ?? 0);
  let total: number | null = null;
  let pagesDone = 0;

  for (;;) {
    if (opts?.signal?.aborted) return;
    const data = await fetchPipelineCatalogResilient(pageSize, offset, sort);
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
