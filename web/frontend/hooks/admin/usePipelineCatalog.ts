'use client';

import { useEffect, useLayoutEffect, useRef, useState, startTransition } from 'react';
import {
  fetchPipelineCatalogPageSingleMode,
  PIPELINE_CATALOG_FIRST_PAGE_ATTEMPTS_LIGHT,
  PIPELINE_CATALOG_FIRST_PAGE_BACKOFF_CAP_MS,
  type PipelineCatalogAttemptInfo,
} from '@/lib/pipelineCatalogFetch';
import {
  readPipelineCatalogCache,
  readPipelineCatalogPeek,
  persistPipelineCatalogPeekFromProducts,
  writePipelineCatalogCache,
  type PipelineCatalogSummaryCached,
} from '@/lib/pipelineCatalogCache';
import { fetchPublicStorefrontListableCount } from '@/lib/refreshStorefrontListableCount';

export type PipelineCatalogSummary = PipelineCatalogSummaryCached;

const CATALOG_FIRST_FETCH = 2;
const CATALOG_BACKGROUND_CHUNK = 12;

export function usePipelineCatalog(pipelineSort: 'newest' | 'shipped_first') {
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [catalogLiveRowCount, setCatalogLiveRowCount] = useState(0);
  const [totalProducts, setTotalProducts] = useState(0);
  const [catalogSummary, setCatalogSummary] = useState<PipelineCatalogSummary | null>(null);
  const [catalogReloadKey, setCatalogReloadKey] = useState(0);
  const [catalogLoadError, setCatalogLoadError] = useState<string | null>(null);
  const [catalogFirstPageFetch, setCatalogFirstPageFetch] = useState<PipelineCatalogAttemptInfo | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const pipelineFetchGenerationRef = useRef(0);

  const reloadCatalog = () => setCatalogReloadKey((k) => k + 1);

  useLayoutEffect(() => {
    const full = readPipelineCatalogCache(pipelineSort);
    const peek = readPipelineCatalogPeek(pipelineSort);
    const fullRows = full?.products ?? [];
    const peekRows = peek?.products ?? [];

    if (full && fullRows.length > 0) {
      setProducts(fullRows);
      setTotalProducts(full.total);
      if (full.catalog_summary) setCatalogSummary(full.catalog_summary);
      setLoading(false);
      setLoadingMore(true);
      setCatalogFirstPageFetch(null);
      setCatalogLiveRowCount(0);
      return;
    }

    if (peek && peekRows.length > 0) {
      setProducts(peekRows);
      setTotalProducts(peek.total);
      if (peek.catalog_summary) setCatalogSummary(peek.catalog_summary);
      setLoading(false);
      setLoadingMore(true);
      setCatalogFirstPageFetch(null);
      setCatalogLiveRowCount(0);
      return;
    }

    setProducts([]);
    setTotalProducts(0);
    setCatalogSummary(null);
    setCatalogLiveRowCount(0);
    setLoading(true);
    setLoadingMore(false);
    setCatalogFirstPageFetch({
      attempt: 0,
      maxAttempts: PIPELINE_CATALOG_FIRST_PAGE_ATTEMPTS_LIGHT,
    });
  }, [pipelineSort, catalogReloadKey]);

  useEffect(() => {
    const myGen = ++pipelineFetchGenerationRef.current;
    const isStale = () => pipelineFetchGenerationRef.current !== myGen;
    let cancelled = false;

    setCatalogLoadError(null);
    setCatalogNotice(null);

    const bootstrap = readPipelineCatalogCache(pipelineSort);
    const peekBoot = readPipelineCatalogPeek(pipelineSort);
    const cacheTail = bootstrap?.products ?? [];
    const hadWarmCache = !!(
      (bootstrap && cacheTail.length > 0) ||
      (peekBoot && (peekBoot.products?.length ?? 0) > 0)
    );
    const trackRetriesOnFirstFetch = !hadWarmCache;

    const mergePreview = (head: typeof cacheTail): any[] => [...head, ...cacheTail.slice(head.length)];

    let cacheWriteTimer: ReturnType<typeof setTimeout> | null = null;
    const bumpCacheWriteLater = (
      merged: typeof cacheTail,
      total: number,
      summary: PipelineCatalogSummary | null,
    ) => {
      if (cacheWriteTimer) clearTimeout(cacheWriteTimer);
      cacheWriteTimer = setTimeout(() => {
        cacheWriteTimer = null;
        if (cancelled || isStale()) return;
        writePipelineCatalogCache({
          sort: pipelineSort,
          total,
          products: merged,
          catalog_summary: summary,
        });
      }, 520);
    };
    const flushCacheWrite = (
      merged: typeof cacheTail,
      total: number,
      summary: PipelineCatalogSummary | null,
    ) => {
      if (cacheWriteTimer) clearTimeout(cacheWriteTimer);
      cacheWriteTimer = null;
      writePipelineCatalogCache({
        sort: pipelineSort,
        total,
        products: merged,
        catalog_summary: summary,
      });
    };

    const refreshStorefrontTotal = () => {
      void fetchPublicStorefrontListableCount().then((n) => {
        if (cancelled || isStale() || n === null) return;
        setCatalogSummary((prev) => {
          const base: PipelineCatalogSummary =
            prev ??
            ({
              total_products: 0,
              shipped_products: 0,
              failed_products: 0,
              storefront_listable_products: n,
              sort: pipelineSort,
            } as PipelineCatalogSummary);
          return { ...base, storefront_listable_products: n };
        });
      });
    };

    (async () => {
      let rowsLoaded = 0;
      let expectedTotal = 0;
      let preferLight = true;
      let fellBackToFullThisSession = false;
      let networkHead: typeof cacheTail = [];
      let lastSummaryState: PipelineCatalogSummary | null = null;

      const loadCatalogPage = async (
        lim: number,
        off: number,
        trackFirstPageRetries: boolean,
      ) => {
        const pageFetchOpts =
          off === 0
            ? {
                maxAttempts: PIPELINE_CATALOG_FIRST_PAGE_ATTEMPTS_LIGHT,
                backoffCapMs: PIPELINE_CATALOG_FIRST_PAGE_BACKOFF_CAP_MS,
              }
            : undefined;
        const reporter = trackFirstPageRetries
          ? (info: PipelineCatalogAttemptInfo) => {
              if (cancelled || isStale()) return;
              setCatalogFirstPageFetch(info);
            }
          : undefined;
        if (preferLight) {
          try {
            return await fetchPipelineCatalogPageSingleMode(
              lim,
              off,
              pipelineSort,
              true,
              reporter,
              pageFetchOpts,
            );
          } catch {
            preferLight = false;
            fellBackToFullThisSession = true;
            return await fetchPipelineCatalogPageSingleMode(
              lim,
              off,
              pipelineSort,
              false,
              reporter,
              pageFetchOpts,
            );
          }
        }
        return await fetchPipelineCatalogPageSingleMode(
          lim,
          off,
          pipelineSort,
          false,
          reporter,
          pageFetchOpts,
        );
      };

      try {
        const first = await loadCatalogPage(CATALOG_FIRST_FETCH, 0, trackRetriesOnFirstFetch);
        if (cancelled || isStale()) return;

        const firstBatch = first.products || [];
        networkHead = firstBatch;
        rowsLoaded = firstBatch.length;
        expectedTotal = typeof first.total === 'number' ? first.total : networkHead.length;
        lastSummaryState =
          first.catalog_summary != null
            ? (first.catalog_summary as PipelineCatalogSummary)
            : bootstrap?.catalog_summary ?? null;

        let knownTotal = first.total ?? firstBatch.length ?? 0;
        const cap0 =
          typeof knownTotal === 'number' && Number.isFinite(knownTotal) && knownTotal >= 0
            ? knownTotal
            : mergePreview(networkHead).length;
        const merged0 = mergePreview(networkHead).slice(0, cap0);
        setProducts(merged0);
        setTotalProducts(knownTotal || merged0.length);
        setCatalogLiveRowCount(networkHead.length);
        if (lastSummaryState) setCatalogSummary(lastSummaryState);
        setLoading(false);
        setCatalogFirstPageFetch(null);
        persistPipelineCatalogPeekFromProducts(
          pipelineSort,
          merged0,
          knownTotal || merged0.length,
          (lastSummaryState ?? peekBoot?.catalog_summary ?? null) as PipelineCatalogSummary | null,
        );

        bumpCacheWriteLater(merged0, knownTotal || merged0.length, lastSummaryState);
        refreshStorefrontTotal();

        let offset = firstBatch.length;
        if (offset < knownTotal) {
          setLoadingMore(true);
        } else {
          setLoadingMore(false);
        }

        while (!cancelled && !isStale() && offset < knownTotal) {
          const next = await loadCatalogPage(CATALOG_BACKGROUND_CHUNK, offset, false);
          if (cancelled || isStale()) return;
          const batch = next.products || [];
          knownTotal = next.total ?? knownTotal;
          expectedTotal = knownTotal;
          if (batch.length === 0) break;
          networkHead = [...networkHead, ...batch];
          rowsLoaded += batch.length;
          if (next.catalog_summary != null) {
            lastSummaryState = next.catalog_summary as PipelineCatalogSummary;
          }
          const cap =
            typeof knownTotal === 'number' && Number.isFinite(knownTotal) && knownTotal >= 0
              ? knownTotal
              : mergePreview(networkHead).length;
          const merged = mergePreview(networkHead).slice(0, cap);
          const totalCopy = knownTotal;

          bumpCacheWriteLater(merged, totalCopy, lastSummaryState);
          startTransition(() => {
            setProducts(merged);
            setTotalProducts(totalCopy);
            setCatalogLiveRowCount(networkHead.length);
            if (lastSummaryState != null) {
              setCatalogSummary(lastSummaryState);
            }
          });
          offset += batch.length;
        }

        const finalCap =
          typeof knownTotal === 'number' && Number.isFinite(knownTotal) && knownTotal >= 0
            ? knownTotal
            : mergePreview(networkHead).length;
        const fullyMerged = mergePreview(networkHead).slice(0, finalCap);
        flushCacheWrite(fullyMerged, knownTotal, lastSummaryState);
        refreshStorefrontTotal();

        if (fellBackToFullThisSession && !cancelled && !isStale()) {
          setCatalogNotice(
            'Using full catalog mode for this load (the fast path was unavailable). Storefront counts and row details match the slower admin path.',
          );
        }
      } catch (e: unknown) {
        if (cancelled || isStale()) return;
        const msg = e instanceof Error ? e.message : String(e);
        if (rowsLoaded > 0 || hadWarmCache) {
          const den = expectedTotal || rowsLoaded || '(unknown)';
          setCatalogLoadError(
            rowsLoaded > 0
              ? `Some catalog pages did not load (${rowsLoaded} of ${den} rows). ${msg}`
              : `Fresh catalog did not reload — still showing cached list. ${msg}`,
          );
        } else {
          setCatalogLoadError(
            `${msg} — both the fast catalog path and the full path failed after automatic retries.`,
          );
        }
      } finally {
        if (cancelled || isStale()) {
          if (cacheWriteTimer) clearTimeout(cacheWriteTimer);
          return;
        }
        setLoading(false);
        setLoadingMore(false);
        setCatalogFirstPageFetch(null);
      }
    })();

    return () => {
      cancelled = true;
      if (cacheWriteTimer) clearTimeout(cacheWriteTimer);
    };
  }, [pipelineSort, catalogReloadKey]);

  return {
    products,
    setProducts,
    loading,
    loadingMore,
    catalogLiveRowCount,
    totalProducts,
    catalogSummary,
    catalogLoadError,
    catalogFirstPageFetch,
    catalogNotice,
    setCatalogNotice,
    reloadCatalog,
    catalogFirstFetch: CATALOG_FIRST_FETCH,
    catalogBackgroundChunk: CATALOG_BACKGROUND_CHUNK,
  };
}
