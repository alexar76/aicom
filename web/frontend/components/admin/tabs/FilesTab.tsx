'use client';

import React, { useEffect, useMemo, useCallback, useRef } from 'react';
import {
  RefreshCw,
  Loader2,
  ChevronDown,
  Maximize2,
  X,
  Download,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { FilterSelect, FilterResetSummary } from '@/components/admin/FilterControls';
import api from '@/lib/api';
import {
  fetchPipelineCatalogAllPages,
} from '@/lib/pipelineCatalogFetch';
import toast from 'react-hot-toast';
import { launchSandboxWithProgress } from '@/lib/sandboxLaunch';
import { sandboxLaunchLabel } from '@/lib/sandboxLaunchI18n';
import { formatDate, localDateInputStartSeconds, localDateInputEndSeconds } from '@/lib/utils';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { useFilesTabStore } from '@/lib/filesTabStore';

/** Match Pipeline tab tiny first page — small batches + visible progress. */
const FILES_CATALOG_PAGE = 2;

const FILE_CATEGORY_COLORS: Record<string, string> = {
  specs: 'from-blue-500 to-blue-600',
  architecture: 'from-purple-500 to-purple-600',
  code: 'from-green-500 to-green-600',
  bugs: 'from-red-500 to-red-600',
  security: 'from-cyan-500 to-cyan-600',
  marketing: 'from-amber-500 to-amber-600',
  telemetry: 'from-pink-500 to-pink-600',
};

type ArtifactsPanelProps = {
  selectedProduct: string;
  files: any[];
  fileLoading: boolean;
  expandedFile: string | null;
  setExpandedFile: (path: string | null) => void;
  fileSearch: string;
  setFileSearch: (v: string) => void;
  fileCategoryFilter: string;
  setFileCategoryFilter: (v: string) => void;
  availableFileCategories: string[];
  filteredFiles: any[];
  truncatedByCategory: Record<string, boolean> | null;
  sandboxIframeSrc: string | null;
  sandboxLoading: boolean;
  sandboxProgress: { percent: number; label: string } | null;
  sandboxError: string | null;
  sandboxReloadKey: number;
  sandboxModalOpen: boolean;
  setSandboxModalOpen: (open: boolean) => void;
  refreshSandbox: () => void;
  ownerZipBusy: boolean;
  onDownloadOwnerArchive: () => void;
};

function ProductArtifactsPanel({
  selectedProduct,
  files,
  fileLoading,
  expandedFile,
  setExpandedFile,
  fileSearch,
  setFileSearch,
  fileCategoryFilter,
  setFileCategoryFilter,
  availableFileCategories,
  filteredFiles,
  truncatedByCategory,
  sandboxIframeSrc,
  sandboxLoading,
  sandboxProgress,
  sandboxError,
  sandboxReloadKey,
  sandboxModalOpen,
  setSandboxModalOpen,
  refreshSandbox,
  ownerZipBusy,
  onDownloadOwnerArchive,
}: ArtifactsPanelProps) {
  const truncatedCats =
    truncatedByCategory && Object.keys(truncatedByCategory).length > 0
      ? Object.keys(truncatedByCategory).sort().join(', ')
      : null;

  const canOpenFullscreen = Boolean(sandboxIframeSrc);

  return (
    <>
      <div className="mb-3 flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!canOpenFullscreen}
            onClick={() => {
              if (!sandboxIframeSrc) return;
              setSandboxModalOpen(true);
            }}
            className="inline-flex items-center justify-center gap-2"
          >
            <Maximize2 className="h-4 w-4" />
            Full screen sandbox
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={ownerZipBusy}
            onClick={() => onDownloadOwnerArchive()}
            className="inline-flex items-center justify-center gap-2"
            title="ZIP: specs, code, QA, marketing/state, telemetry — factory owner export (operator+)"
          >
            {ownerZipBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Download product ZIP
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={sandboxLoading}
            onClick={() => void refreshSandbox()}
            className="inline-flex items-center gap-2 text-gray-300"
          >
            {sandboxLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
        <p className="max-w-xl text-xs text-gray-500">
          Preview loads below. Full screen opens in this page (no popup) so the browser does not block it.{' '}
          <span className="text-gray-400">
            «Download product ZIP» packs the same on-disk tree as this tab (plus a pipeline snapshot in EXPORT_MANIFEST.json)
            — before or after storefront listing; requires operator / admin / super_admin.
          </span>
        </p>
      </div>

      <div className="mb-3 overflow-hidden rounded-xl border border-white/10 bg-black/40">
        {sandboxLoading && !sandboxIframeSrc ? (
          <div className="flex aspect-video min-h-[200px] flex-col items-center justify-center gap-3 px-6 text-sm text-gray-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>{sandboxProgress?.label ?? 'Starting sandbox…'}</span>
            {sandboxProgress ? (
              <ProgressBar value={sandboxProgress.percent} max={100} className="w-full max-w-xs h-2" showValue />
            ) : null}
          </div>
        ) : sandboxError ? (
          <div className="flex aspect-video min-h-[200px] flex-col items-center justify-center gap-2 px-4 text-center text-sm text-red-300">
            <span>{sandboxError}</span>
            <Button type="button" variant="secondary" size="sm" onClick={() => void refreshSandbox()}>
              Retry
            </Button>
          </div>
        ) : sandboxIframeSrc ? (
          <div className="relative aspect-video h-[min(40vh,320px)] w-full sm:h-[min(45vh,380px)]">
            <iframe
              key={`prev-${sandboxReloadKey}`}
              title="Sandbox preview"
              src={sandboxIframeSrc}
              className="h-full w-full border-0 bg-black"
              referrerPolicy="no-referrer"
            />
            {sandboxLoading ? (
              <div className="absolute inset-0 flex items-center justify-center bg-black/55 backdrop-blur-[1px]">
                <Loader2 className="h-8 w-8 animate-spin text-white" />
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex aspect-video min-h-[200px] flex-col items-center justify-center gap-3 px-4 text-center text-sm text-gray-500">
            {fileLoading ? (
              <span>Preview is available after the file list loads.</span>
            ) : files.length === 0 ? (
              <span>No files to preview for this product.</span>
            ) : (
              <>
                <p className="max-w-md text-gray-400">
                  Live sandbox is not started automatically so the file list opens quickly. Load it when you need the
                  iframe.
                </p>
                <Button type="button" variant="secondary" size="sm" onClick={() => void refreshSandbox()}>
                  Load sandbox preview
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {sandboxModalOpen && sandboxIframeSrc ? (
        <div
          className="fixed inset-0 z-[100] flex flex-col bg-zinc-950/95 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Sandbox full screen"
        >
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
            <span className="truncate text-sm font-medium text-white">
              Sandbox · {selectedProduct.slice(0, 14)}…
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={sandboxLoading}
                onClick={() => void refreshSandbox()}
                className="inline-flex items-center gap-2"
              >
                {sandboxLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Reload
              </Button>
              <button
                type="button"
                onClick={() => setSandboxModalOpen(false)}
                className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"
                aria-label="Close sandbox"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="relative flex min-h-0 flex-1 flex-col">
            <iframe
              key={`modal-${sandboxReloadKey}`}
              title="Sandbox full screen"
              src={sandboxIframeSrc}
              className="min-h-0 w-full flex-1 border-0 bg-black"
              referrerPolicy="no-referrer"
            />
            {sandboxLoading ? (
              <div className="absolute inset-0 flex items-center justify-center bg-black/45 backdrop-blur-[1px]">
                <Loader2 className="h-10 w-10 animate-spin text-white" />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Input
          value={fileSearch}
          onChange={(e) => setFileSearch(e.target.value)}
          placeholder="Search filename/path/content preview..."
        />
        <FilterSelect value={fileCategoryFilter} onChange={(e) => setFileCategoryFilter(e.target.value)}>
          <option value="all">All categories</option>
          {availableFileCategories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </FilterSelect>
        <FilterResetSummary
          onReset={() => {
            setFileSearch('');
            setFileCategoryFilter('all');
          }}
          resetLabel="Reset file filters"
          summary={`Showing ${filteredFiles.length} of ${files.length}`}
        />
      </div>
      {truncatedCats ? (
        <p className="mb-3 text-xs text-amber-200/90">
          File list hit the per-category cap for: {truncatedCats}. Deeper paths under vendor dirs (e.g. node_modules) are
          skipped.
        </p>
      ) : null}
      {fileLoading ? (
        <div className="text-gray-400">Loading files…</div>
      ) : files.length === 0 ? (
        <div className="text-gray-500 py-6 text-center text-sm">No files found for this product</div>
      ) : filteredFiles.length === 0 ? (
        <div className="text-gray-500 py-6 text-center text-sm">No files match current filters</div>
      ) : (
        <>
          <h3 className="mb-2 text-sm font-medium text-gray-400">
            {filteredFiles.length} file{filteredFiles.length !== 1 ? 's' : ''} for {selectedProduct.slice(0, 12)}…
          </h3>
          <div className="max-h-[min(55vh,480px)] space-y-2 overflow-y-auto pr-1 md:max-h-[min(65vh,560px)]">
            {filteredFiles.map((file: any) => (
              <GlassCard key={file.path} className="overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpandedFile(expandedFile === file.path ? null : file.path)}
                  className="flex w-full flex-col gap-2 p-3 text-left sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div
                      className={`h-2 w-2 shrink-0 rounded-full bg-gradient-to-br ${
                        FILE_CATEGORY_COLORS[file.category] || 'from-gray-500 to-gray-600'
                      }`}
                    />
                    <div className="min-w-0">
                      <span className="text-sm font-medium text-white">{file.filename}</span>
                      <span className="ml-2 text-xs text-gray-500">({(file.size_bytes / 1024).toFixed(1)} KB)</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 sm:ml-2">
                    <span className="rounded bg-white/5 px-2 py-0.5 text-xs text-gray-500">{file.category}</span>
                    <span className="text-xs text-gray-500">{expandedFile === file.path ? '▲' : '▼'}</span>
                  </div>
                </button>
                {expandedFile === file.path && (
                  <div className="border-t border-white/5">
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-gray-300">
                      {file.error ? (
                        <span className="text-red-400">Error: {file.error}</span>
                      ) : (
                        file.preview
                      )}
                    </pre>
                  </div>
                )}
              </GlassCard>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export function FilesTab({ locale }: { locale: AdminLocale }) {
  const {
    products,
    setProducts,
    selectedProduct,
    setSelectedProduct,
    files,
    setFiles,
    truncatedByCategory,
    setTruncatedByCategory,
    catalogInitialLoading,
    setCatalogInitialLoading,
    catalogLoadingMore,
    setCatalogLoadingMore,
    catalogTotal,
    setCatalogTotal,
    lastCatalogBatchSize,
    setLastCatalogBatchSize,
    catalogProgress,
    setCatalogProgress,
    productsLoadError,
    setProductsLoadError,
    productsReloadKey,
    setProductsReloadKey,
    fileLoading,
    setFileLoading,
    expandedFile,
    setExpandedFile,
    sandboxIframeSrc,
    setSandboxIframeSrc,
    sandboxLoading,
    setSandboxLoading,
    sandboxProgress,
    setSandboxProgress,
    sandboxError,
    setSandboxError,
    sandboxReloadKey,
    setSandboxReloadKey,
    sandboxModalOpen,
    setSandboxModalOpen,
    productSearch,
    setProductSearch,
    productStateFilter,
    setProductStateFilter,
    createdFrom,
    setCreatedFrom,
    createdTo,
    setCreatedTo,
    fileSearch,
    setFileSearch,
    fileCategoryFilter,
    setFileCategoryFilter,
    ownerZipBusy,
    setOwnerZipBusy,
  } = useFilesTabStore();
  const productsRef = useRef<any[]>([]);
  const productListScrollRef = useRef<HTMLDivElement>(null);
  const catalogSentinelRef = useRef<HTMLDivElement>(null);
  const catalogEpochRef = useRef(0);

  productsRef.current = products;

  const catalogHasMore = useMemo(() => {
    if (catalogTotal != null) return products.length < catalogTotal;
    return lastCatalogBatchSize >= FILES_CATALOG_PAGE;
  }, [catalogTotal, products.length, lastCatalogBatchSize]);

  useEffect(() => {
    const ac = new AbortController();
    catalogEpochRef.current += 1;
    const epoch = catalogEpochRef.current;

    setCatalogInitialLoading(true);
    setCatalogLoadingMore(false);
    setProducts([]);
    setCatalogTotal(null);
    setLastCatalogBatchSize(0);
    setProductsLoadError(null);
    setSelectedProduct(null);
    setFiles([]);
    setTruncatedByCategory(null);
    setSandboxIframeSrc(null);
    setSandboxError(null);
    setSandboxModalOpen(false);
    setSandboxReloadKey(0);
    setCatalogProgress(null);

    void (async () => {
      try {
        await fetchPipelineCatalogAllPages('shipped_first', {
          signal: ac.signal,
          startOffset: 0,
          maxPages: 1,
          pageSize: FILES_CATALOG_PAGE,
          onPage: ({ batch, loaded, total }) => {
            if (ac.signal.aborted || catalogEpochRef.current !== epoch) return;
            setProducts(batch);
            setCatalogProgress({ loaded, total });
            if (typeof total === 'number') setCatalogTotal(total);
            setLastCatalogBatchSize(batch.length);
          },
        });
      } catch (e: unknown) {
        if (ac.signal.aborted || catalogEpochRef.current !== epoch) return;
        setProductsLoadError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!ac.signal.aborted && catalogEpochRef.current === epoch) {
          setCatalogInitialLoading(false);
          setCatalogLoadingMore(false);
        }
      }
    })();

    return () => ac.abort();
  }, [productsReloadKey]);

  const loadMoreCatalog = useCallback(async () => {
    if (!catalogHasMore || catalogInitialLoading || catalogLoadingMore) return;
    const epoch = catalogEpochRef.current;
    const startOffset = productsRef.current.length;
    setCatalogLoadingMore(true);
    try {
      await fetchPipelineCatalogAllPages('shipped_first', {
        startOffset,
        maxPages: 1,
        pageSize: FILES_CATALOG_PAGE,
        onPage: ({ batch, loaded, total }) => {
          if (catalogEpochRef.current !== epoch) return;
          setProducts((prev) => [...prev, ...batch]);
          setCatalogProgress({ loaded, total });
          if (typeof total === 'number') setCatalogTotal(total);
          setLastCatalogBatchSize(batch.length);
        },
      });
    } catch (e: unknown) {
      if (catalogEpochRef.current === epoch) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (catalogEpochRef.current === epoch) {
        setCatalogLoadingMore(false);
      }
    }
  }, [catalogHasMore, catalogInitialLoading, catalogLoadingMore]);

  const FILES_FETCH_MS = 120_000;
  const FILES_ATTEMPTS = 5;

  const loadFiles = async (productId: string) => {
    setSelectedProduct(productId);
    setFileLoading(true);
    setExpandedFile(null);
    setSandboxIframeSrc(null);
    setSandboxError(null);
    setSandboxModalOpen(false);
    setSandboxReloadKey(0);
    setSandboxLoading(false);
    const token = localStorage.getItem('admin_token');
    let lastErr: unknown;
    for (let attempt = 0; attempt < FILES_ATTEMPTS; attempt++) {
      try {
        const res = await fetch(`/api/admin/products/${productId}/files`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(FILES_FETCH_MS),
        });
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const errBody = await res.json();
            if (errBody?.detail) detail = String(errBody.detail);
          } catch {
            /* ignore */
          }
          throw new Error(detail);
        }
        const data = await res.json();
        if (typeof data.count === 'number' && data.count > 0 && !(data.files?.length)) {
          throw new Error('API returned count but empty files array');
        }
        setFiles(data.files || []);
        setTruncatedByCategory(
          data.truncated_by_category && typeof data.truncated_by_category === 'object'
            ? data.truncated_by_category
            : null,
        );
        setFileLoading(false);
        return;
      } catch (e) {
        lastErr = e;
        if (attempt < FILES_ATTEMPTS - 1) {
          await new Promise((r) => setTimeout(r, Math.min(8000, 400 * 2 ** attempt)));
        }
      }
    }
    setFiles([]);
    setTruncatedByCategory(null);
    setSandboxIframeSrc(null);
    setSandboxError(null);
    setSandboxLoading(false);
    setFileLoading(false);
    const msg = lastErr instanceof Error ? lastErr.message : String(lastErr);
    toast.error(`Could not load files: ${msg}`);
  };

  const toggleProduct = (id: string) => {
    if (selectedProduct === id) {
      setSelectedProduct(null);
      setFiles([]);
      setTruncatedByCategory(null);
      setExpandedFile(null);
      setSandboxIframeSrc(null);
      setSandboxError(null);
      setSandboxModalOpen(false);
      setSandboxReloadKey(0);
      setSandboxLoading(false);
      return;
    }
    void loadFiles(id);
  };

  const refreshSandbox = useCallback(async () => {
    if (!selectedProduct) return;
    setSandboxLoading(true);
    setSandboxProgress({ percent: 5, label: sandboxLaunchLabel(locale, 'starting') });
    setSandboxError(null);
    try {
      const result = await launchSandboxWithProgress(
        selectedProduct,
        { locale },
        setSandboxProgress,
      );
      const raw = result.url || `/api/sandbox/view/${result.sandbox_id}`;
      const abs = raw.startsWith('http') ? raw : new URL(raw, window.location.origin).href;
      setSandboxIframeSrc(abs);
      setSandboxReloadKey((k) => k + 1);
    } catch (e: unknown) {
      setSandboxIframeSrc(null);
      const msg = e instanceof Error ? e.message : 'Failed to start sandbox';
      setSandboxError(msg);
      toast.error(msg);
    } finally {
      setSandboxLoading(false);
      setSandboxProgress(null);
    }
  }, [locale, selectedProduct]);

  const downloadOwnerArchive = useCallback(async () => {
    if (!selectedProduct) return;
    setOwnerZipBusy(true);
    try {
      await api.downloadAdminProductOwnerZip(selectedProduct);
      toast.success('Product archive downloaded');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setOwnerZipBusy(false);
    }
  }, [selectedProduct]);

  useEffect(() => {
    if (!sandboxModalOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSandboxModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sandboxModalOpen]);

  const filteredProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    const start = localDateInputStartSeconds(createdFrom);
    const end = localDateInputEndSeconds(createdTo);
    return products.filter((p: any) => {
      const st = String(p?.state || '').toUpperCase();
      if (productStateFilter !== 'all' && st !== productStateFilter) return false;

      if (start != null || end != null) {
        const raw = Number(p?.created_at) || 0;
        const createdSec = raw > 1e12 ? raw / 1000 : raw;
        if (!createdSec) return false;
        if (start != null && createdSec < start) return false;
        if (end != null && createdSec > end) return false;
      }

      if (!q) return true;
      const idea = String(p?.idea || '').toLowerCase();
      const id = String(p?.id || '').toLowerCase();
      return idea.includes(q) || id.includes(q);
    });
  }, [products, productSearch, productStateFilter, createdFrom, createdTo]);

  useEffect(() => {
    const root = productListScrollRef.current;
    const target = catalogSentinelRef.current;
    if (!root || !target || !catalogHasMore || filteredProducts.length === 0) return;

    const obs = new IntersectionObserver(
      (entries) => {
        const hit = entries.some((en) => en.isIntersecting);
        if (!hit) return;
        void loadMoreCatalog();
      },
      { root, rootMargin: '240px', threshold: 0 },
    );
    obs.observe(target);
    return () => obs.disconnect();
  }, [catalogHasMore, loadMoreCatalog, products.length, filteredProducts.length]);

  const availableProductStates = useMemo(() => {
    const s = new Set<string>();
    for (const p of products) {
      const st = String(p?.state || '').toUpperCase();
      if (st) s.add(st);
    }
    return Array.from(s).sort();
  }, [products]);

  const availableFileCategories = useMemo(() => {
    const s = new Set<string>();
    for (const f of files) {
      const c = String(f?.category || '');
      if (c) s.add(c);
    }
    return Array.from(s).sort();
  }, [files]);

  const filteredFiles = useMemo(() => {
    const q = fileSearch.trim().toLowerCase();
    return files.filter((file: any) => {
      if (fileCategoryFilter !== 'all' && String(file?.category || '') !== fileCategoryFilter) return false;
      if (!q) return true;
      const filename = String(file?.filename || '').toLowerCase();
      const path = String(file?.path || '').toLowerCase();
      const preview = String(file?.preview || '').toLowerCase();
      return filename.includes(q) || path.includes(q) || preview.includes(q);
    });
  }, [files, fileSearch, fileCategoryFilter]);

  const artifactsPanel =
    selectedProduct != null ? (
      <ProductArtifactsPanel
        selectedProduct={selectedProduct}
        files={files}
        fileLoading={fileLoading}
        expandedFile={expandedFile}
        setExpandedFile={setExpandedFile}
        fileSearch={fileSearch}
        setFileSearch={setFileSearch}
        fileCategoryFilter={fileCategoryFilter}
        setFileCategoryFilter={setFileCategoryFilter}
        availableFileCategories={availableFileCategories}
        filteredFiles={filteredFiles}
        truncatedByCategory={truncatedByCategory}
        sandboxIframeSrc={sandboxIframeSrc}
        sandboxLoading={sandboxLoading}
        sandboxProgress={sandboxProgress}
        sandboxError={sandboxError}
        sandboxReloadKey={sandboxReloadKey}
        sandboxModalOpen={sandboxModalOpen}
        setSandboxModalOpen={setSandboxModalOpen}
        refreshSandbox={refreshSandbox}
        ownerZipBusy={ownerZipBusy}
        onDownloadOwnerArchive={() => void downloadOwnerArchive()}
      />
    ) : null;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">{t(locale, 'files.page.title')}</h2>
      <p className="text-sm text-gray-400">{t(locale, 'files.page.subtitle')}</p>

      {catalogInitialLoading && products.length === 0 ? (
        <GlassCard className="p-4">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <Loader2 className="h-5 w-5 shrink-0 animate-spin text-indigo-400" aria-hidden />
              <span>
                Loading product catalog — <span className="text-indigo-200">{FILES_CATALOG_PAGE}</span> products per
                request (same idea as Pipeline first paint)
              </span>
            </div>
            {catalogProgress != null &&
            catalogProgress.total != null &&
            catalogProgress.total > 0 ? (
              <>
                <ProgressBar
                  value={Math.min(
                    100,
                    Math.round((catalogProgress.loaded / catalogProgress.total) * 100),
                  )}
                  label={`${catalogProgress.loaded} / ${catalogProgress.total} products in index`}
                  variant="primary"
                />
                <p className="text-center text-xs text-gray-500">
                  {Math.min(100, Math.round((catalogProgress.loaded / catalogProgress.total) * 100))}% of catalog
                  rows loaded — scroll the list or use &quot;Load more&quot; for the rest.
                </p>
              </>
            ) : (
              <p className="text-xs text-gray-500">Waiting for the first batch from the server…</p>
            )}
          </div>
        </GlassCard>
      ) : productsLoadError && products.length === 0 ? (
        <div className="space-y-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
          <p className="text-sm text-amber-100/90">
            Could not load the product list (server busy or timeout). You can retry without refreshing the page.
          </p>
          <p className="break-all font-mono text-xs text-amber-200/70">{productsLoadError}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setProductsReloadKey((k) => k + 1)}
            className="inline-flex items-center gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      ) : products.length === 0 ? (
        <div className="text-gray-500">No products found. Create a product first.</div>
      ) : (
        <div className="space-y-4">
          {catalogLoadingMore && catalogProgress ? (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-xs text-gray-500">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-indigo-400" aria-hidden />
                Loading more products…
              </p>
              {catalogProgress.total != null && catalogProgress.total > 0 ? (
                <>
                  <ProgressBar
                    value={Math.min(
                      100,
                      Math.round((catalogProgress.loaded / catalogProgress.total) * 100),
                    )}
                    label={`${catalogProgress.loaded} / ${catalogProgress.total} products`}
                    variant="primary"
                  />
                  <p className="text-center text-[11px] text-gray-500">
                    {Math.min(100, Math.round((catalogProgress.loaded / catalogProgress.total) * 100))}% of catalog
                  </p>
                </>
              ) : (
                <p className="text-[11px] text-gray-600">{catalogProgress.loaded} rows loaded so far</p>
              )}
            </div>
          ) : catalogHasMore && products.length > 0 ? (
            <p className="text-xs text-gray-600">
              Not all products are loaded yet — scroll the list or use &quot;Load more&quot; below.
            </p>
          ) : null}

          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-400">Products</h3>
            <Input
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
              placeholder="Search products..."
            />
            <select
              value={productStateFilter}
              onChange={(e) => setProductStateFilter(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none"
            >
              <option value="all">All states</option>
              {availableProductStates.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
            <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
              <span>Created from (local day)</span>
              <input
                type="date"
                value={createdFrom}
                onChange={(e) => setCreatedFrom(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
              <span>Created to (local day)</span>
              <input
                type="date"
                value={createdTo}
                onChange={(e) => setCreatedTo(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none"
              />
            </label>
            <p className="text-[11px] text-gray-500">
              Showing {filteredProducts.length} of {products.length} loaded
            </p>
            <button
              type="button"
              onClick={() => {
                setProductSearch('');
                setProductStateFilter('all');
                setCreatedFrom('');
                setCreatedTo('');
              }}
              className="text-[11px] text-indigo-300 underline underline-offset-2 hover:text-indigo-200"
            >
              Reset product filters
            </button>
          </div>

          <div className="items-start gap-6 md:grid md:grid-cols-3">
            <div className="flex min-h-0 flex-col gap-2 md:col-span-1">
              <div
                ref={productListScrollRef}
                className="max-h-[min(50vh,420px)] space-y-2 overflow-y-auto pr-1 md:max-h-[min(72vh,640px)]"
              >
                {filteredProducts.map((p: any) => {
                  const open = selectedProduct === p.id;
                  return (
                    <div
                      key={p.id}
                      className={`overflow-hidden rounded-xl border transition-colors ${
                        open ? 'border-indigo-500/40 bg-indigo-500/10' : 'border-white/10 bg-white/[0.02]'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => toggleProduct(p.id)}
                        className="flex w-full items-start gap-2 p-3 text-left text-sm"
                      >
                        <ChevronDown
                          className={`mt-0.5 h-4 w-4 shrink-0 text-gray-500 transition-transform md:hidden ${
                            open ? 'rotate-180' : ''
                          }`}
                          aria-hidden
                        />
                        <div className="min-w-0 flex-1">
                          <div className={`font-medium ${open ? 'text-indigo-200' : 'text-gray-200'}`}>
                            {p.idea || p.id}
                          </div>
                          <div className="mt-1 text-xs opacity-60">
                            {p.state} · {p.id?.slice(0, 12)}
                            {(() => {
                              const raw = Number(p?.created_at) || 0;
                              const sec = raw > 1e12 ? raw / 1000 : raw;
                              if (!sec) return null;
                              return (
                                <>
                                  {' '}
                                  · created {formatDate(sec)}
                                </>
                              );
                            })()}
                          </div>
                        </div>
                      </button>
                      {open && (
                        <div className="border-t border-white/10 p-3 md:hidden">{artifactsPanel}</div>
                      )}
                    </div>
                  );
                })}
                {catalogHasMore ? (
                  <div className="flex flex-col items-stretch gap-2 border-t border-white/5 pt-2">
                    <div ref={catalogSentinelRef} className="h-2 w-full shrink-0" aria-hidden />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={catalogLoadingMore || catalogInitialLoading}
                      onClick={() => void loadMoreCatalog()}
                      className="inline-flex items-center justify-center gap-2 text-indigo-200 hover:text-white"
                    >
                      {catalogLoadingMore ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Loading more…
                        </>
                      ) : (
                        <>Load more products ({products.length} loaded)</>
                      )}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-6 hidden min-h-0 md:col-span-2 md:mt-0 md:block">
              {!selectedProduct ? (
                <div className="py-12 text-center text-gray-500">Select a product to browse its files</div>
              ) : (
                artifactsPanel
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
