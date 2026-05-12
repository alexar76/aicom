'use client';

import React, { useEffect, useState, useMemo } from 'react';
import {
  RefreshCw,
  ExternalLink,
  Loader2,
  ChevronDown,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { FilterSelect, FilterResetSummary } from '@/components/admin/FilterControls';
import api from '@/lib/api';
import {
  fetchPipelineCatalogAllPages,
  PIPELINE_CATALOG_MAX_PAGE,
} from '@/lib/pipelineCatalogFetch';
import toast from 'react-hot-toast';

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
  sandboxOpening: boolean;
  openSandboxPreview: () => void;
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
  sandboxOpening,
  openSandboxPreview,
}: ArtifactsPanelProps) {
  return (
    <>
      <div className="mb-3 flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={sandboxOpening}
          onClick={() => void openSandboxPreview()}
          className="flex w-full items-center justify-center gap-2 sm:w-auto"
        >
          {sandboxOpening ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ExternalLink className="w-4 h-4" />
          )}
          {sandboxOpening ? 'Starting…' : 'Open sandbox preview'}
        </Button>
        <p className="max-w-xl text-xs text-gray-500">
          Starts a sandbox for this product and opens the HTML demo (iframe) in a new tab — same viewer as the product page.
        </p>
      </div>
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

export function FilesTab() {
  const [products, setProducts] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingMoreCatalog, setLoadingMoreCatalog] = useState(false);
  const [catalogProgress, setCatalogProgress] = useState<{ loaded: number; total: number | null } | null>(null);
  const [productsLoadError, setProductsLoadError] = useState<string | null>(null);
  const [productsReloadKey, setProductsReloadKey] = useState(0);
  const [fileLoading, setFileLoading] = useState(false);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [sandboxOpening, setSandboxOpening] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productStateFilter, setProductStateFilter] = useState('all');
  const [fileSearch, setFileSearch] = useState('');
  const [fileCategoryFilter, setFileCategoryFilter] = useState('all');

  useEffect(() => {
    const ac = new AbortController();
    setLoadingCatalog(true);
    setLoadingMoreCatalog(false);
    setProducts([]);
    setCatalogProgress(null);
    setProductsLoadError(null);
    setSelectedProduct(null);
    setFiles([]);

    void (async () => {
      try {
        let first = true;
        await fetchPipelineCatalogAllPages('shipped_first', {
          signal: ac.signal,
          onPage: ({ batch, loaded, total }) => {
            if (ac.signal.aborted) return;
            setProducts((prev) => [...prev, ...batch]);
            setCatalogProgress({ loaded, total });
            if (first && batch.length > 0) {
              first = false;
              setLoadingCatalog(false);
              setLoadingMoreCatalog(true);
            }
          },
        });
        if (ac.signal.aborted) return;
        setLoadingMoreCatalog(false);
        setLoadingCatalog(false);
      } catch (e: unknown) {
        if (ac.signal.aborted) return;
        setProductsLoadError(e instanceof Error ? e.message : String(e));
        setLoadingCatalog(false);
        setLoadingMoreCatalog(false);
      }
    })();

    return () => ac.abort();
  }, [productsReloadKey]);

  const FILES_FETCH_MS = 120_000;
  const FILES_ATTEMPTS = 5;

  const loadFiles = async (productId: string) => {
    setSelectedProduct(productId);
    setFileLoading(true);
    setExpandedFile(null);
    const token = localStorage.getItem('admin_token');
    let lastErr: unknown;
    for (let attempt = 0; attempt < FILES_ATTEMPTS; attempt++) {
      try {
        const res = await fetch(`/api/admin/products/${productId}/files`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(FILES_FETCH_MS),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setFiles(data.files || []);
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
    setFileLoading(false);
    const msg = lastErr instanceof Error ? lastErr.message : String(lastErr);
    toast.error(`Could not load files: ${msg}`);
  };

  const toggleProduct = (id: string) => {
    if (selectedProduct === id) {
      setSelectedProduct(null);
      setFiles([]);
      setExpandedFile(null);
      return;
    }
    void loadFiles(id);
  };

  const openSandboxPreview = async () => {
    if (!selectedProduct) return;
    setSandboxOpening(true);
    try {
      const result = await api.startSandbox(selectedProduct);
      const raw = result.url || `/api/sandbox/view/${result.sandbox_id}`;
      const abs = raw.startsWith('http') ? raw : new URL(raw, window.location.origin).href;
      const win = window.open(abs, '_blank', 'noopener,noreferrer');
      if (!win) {
        toast.error('Popup blocked — allow popups for this site or open the URL manually.');
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to start sandbox');
    } finally {
      setSandboxOpening(false);
    }
  };

  const filteredProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    return products.filter((p: any) => {
      const st = String(p?.state || '').toUpperCase();
      if (productStateFilter !== 'all' && st !== productStateFilter) return false;
      if (!q) return true;
      const idea = String(p?.idea || '').toLowerCase();
      const id = String(p?.id || '').toLowerCase();
      return idea.includes(q) || id.includes(q);
    });
  }, [products, productSearch, productStateFilter]);

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
        sandboxOpening={sandboxOpening}
        openSandboxPreview={() => void openSandboxPreview()}
      />
    ) : null;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Generated Files Browser</h2>
      <p className="text-sm text-gray-400">Browse all artifacts generated by the AI pipeline for each product.</p>

      {loadingCatalog && products.length === 0 ? (
        <div className="text-gray-400">Loading products…</div>
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
          {(loadingCatalog || loadingMoreCatalog) &&
            catalogProgress &&
            (catalogProgress.total == null || catalogProgress.loaded < catalogProgress.total) && (
            <p className="text-xs text-gray-500">
              Loading catalog… {catalogProgress.loaded}
              {catalogProgress.total != null ? ` / ${catalogProgress.total}` : ''} (up to {PIPELINE_CATALOG_MAX_PAGE} per request)
            </p>
          )}

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
            <p className="text-[11px] text-gray-500">
              Showing {filteredProducts.length} of {products.length} loaded
            </p>
            <button
              type="button"
              onClick={() => {
                setProductSearch('');
                setProductStateFilter('all');
              }}
              className="text-[11px] text-indigo-300 underline underline-offset-2 hover:text-indigo-200"
            >
              Reset product filters
            </button>
          </div>

          <div className="items-start gap-6 md:grid md:grid-cols-3">
            <div className="flex min-h-0 flex-col gap-2 md:col-span-1">
              <div className="max-h-[min(50vh,420px)] space-y-2 overflow-y-auto pr-1 md:max-h-[min(72vh,640px)]">
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
                          </div>
                        </div>
                      </button>
                      {open && (
                        <div className="border-t border-white/10 p-3 md:hidden">{artifactsPanel}</div>
                      )}
                    </div>
                  );
                })}
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
