'use client';

import React, { useEffect, useLayoutEffect, useState, useRef, useMemo, startTransition } from 'react';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Cpu,
  Bot,
  Shield,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Plus,
  Send,
  Activity,
  Users,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  MessageCircle,
  Menu,
  X,
  Trash2,
  Edit3,
  RefreshCw,
  Globe,
  ToggleLeft,
  ToggleRight,
  Save,
  List,
  ScrollText,
  ChevronRight,
  Terminal,
  Radio,
  Pause,
  Play,
  Gauge,
  Circle,
  Star,
  ExternalLink,
  Zap,
  GitBranch,
  Container,
  Layers,
  FlaskConical,
  BrainCircuit,
  ClipboardList,
  Inbox,
  Megaphone,
  Store,
  Upload,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import {
  FilterControlsPanel,
  FilterNumberInput,
  FilterResetSummary,
  FilterSelect,
} from '@/components/admin/FilterControls';
import BrainstormingTab from '@/components/BrainstormingTab';
import SupportQueueTab from '@/components/SupportQueueTab';
import OutreachTab from '@/components/OutreachTab';
import { QRCodeSVG } from 'qrcode.react';
import api, {
  DashboardData,
  ProviderStatus,
  AgentStatus,
  CreateProviderPayload,
  RoutingRule,
  ChatMessage,
  DemoReplayAdminConfig,
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, applyTheme, formatDate } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import { CATEGORY_LABELS, CATEGORY_COLORS, STAGE_AGENT_TITLE } from './pipelineConstants';
import { ProductPulse, type ProductPulsePayload } from './ProductPulse';
import { HumanReviewGatePanel } from './HumanReviewGatePanel';
import { StorefrontFollowupPanel } from './StorefrontFollowupPanel';
import {
  PIPELINE_CATEGORY_FILTER_ORDER,
  bucketPipelineProductForCategoryFilter,
} from '@/lib/pipelineCategoryBucket';
import { usePipelineCatalog } from '@/hooks/admin/usePipelineCatalog';
import { usePipelineFilters } from '@/hooks/admin/usePipelineFilters';
import { usePipelineModals } from '@/hooks/admin/usePipelineModals';
import { usePipelineProductPulses } from '@/hooks/admin/usePipelineProductPulses';
import { PipelineOnboardingCoach } from '@/components/admin/pipeline/PipelineOnboardingCoach';
import { PipelineProductFailedPanel } from '@/components/admin/pipeline/PipelineProductFailedPanel';
import {
  findTaskForStage,
  formatTaskDuration,
  formatTaskWhen,
  pipelineAgentEmoji,
  safeJson,
  toUnixSeconds,
} from '@/lib/pipelineProductHelpers';

export function PipelineTab() {
  const [pipelineSort, setPipelineSort] = useState<'newest' | 'shipped_first'>('shipped_first');

  const catalog = usePipelineCatalog(pipelineSort);
  const {
    products,
    setProducts,
    loading,
    loadingMore,
    totalProducts,
    catalogSummary,
    catalogLoadError,
    catalogFirstPageFetch,
    catalogNotice,
    setCatalogNotice,
    reloadCatalog,
    catalogFirstFetch: CATALOG_FIRST_FETCH,
    catalogBackgroundChunk: CATALOG_BACKGROUND_CHUNK,
    catalogLiveRowCount,
  } = catalog;

  const filters = usePipelineFilters(products, totalProducts, loadingMore);
  const {
    activeCategory,
    setActiveCategory,
    productSearch,
    setProductSearch,
    stateFilter,
    setStateFilter,
    storefrontFilter,
    setStorefrontFilter,
    createdFrom,
    setCreatedFrom,
    createdTo,
    setCreatedTo,
    stateFilterOptions,
    pipelineCategoryCounts,
    pipelineCategoryCountsReady,
    pipelineCategoryCountsPartial,
    filteredProducts,
    resetFilters,
  } = filters;

  const modals = usePipelineModals();
  const {
    expandedProduct,
    setExpandedProduct,
    expandedFailureProduct,
    setExpandedFailureProduct,
    specModalProduct,
    setSpecModalProduct,
    specData,
    specLoading,
    loadSpec,
    closeSpecModal,
    handoffModalProduct,
    setHandoffModalProduct,
    handoffData,
    handoffLoading,
    loadDeveloperHandoff,
    closeHandoffModal,
    taskStageModal,
    setTaskStageModal,
    openTaskDetailModal,
  } = modals;

  usePipelineProductPulses(setProducts);

  const mergeProductPatch = (productId: string, patch: Record<string, unknown>) => {
    setProducts((prev) => prev.map((p) => (p.id === productId ? { ...p, ...patch } : p)));
  };

  /** Loaded catalog rows vs server total — use this for any “% of catalog” display (not HTTP retry index). */
  const catalogHydrationPercent = useMemo(() => {
    if (!totalProducts || totalProducts <= 0) return 0;
    return Math.min(100, Math.round((products.length / totalProducts) * 100));
  }, [products.length, totalProducts]);

  /** First HTTP page: bar reflects which retry we are on (API busy / timeout), not row hydration. */
  const firstCatalogPageProgressPct = useMemo(() => {
    if (!catalogFirstPageFetch) return 0;
    const { attempt, maxAttempts, lastError, backoffMs } = catalogFirstPageFetch;
    if (!maxAttempts || maxAttempts <= 0) return 0;
    const base = (attempt / maxAttempts) * 100;
    const inBackoff = Boolean(lastError && backoffMs != null && backoffMs > 0);
    const bump = inBackoff ? Math.min(10, 100 / maxAttempts) : 0;
    return Math.min(95, Math.round(base + bump));
  }, [catalogFirstPageFetch]);

  /** Task queue rows summed across already-loaded catalog products (Pipeline API embeds tasks per row). */
  const pipelineLoadedTaskStats = useMemo(() => {
    let total = 0;
    let completed = 0;
    let running = 0;
    let pending = 0;
    let failed = 0;
    for (const p of products) {
      const tc = (p as { task_counts?: Record<string, unknown> }).task_counts;
      if (!tc || typeof tc !== 'object') continue;
      total += Number(tc.total) || 0;
      completed += Number(tc.completed) || 0;
      running += Number(tc.running) || 0;
      pending += Number(tc.pending) || 0;
      failed += Number(tc.failed) || 0;
    }
    return { total, completed, running, pending, failed };
  }, [products]);

  const pipelineLoadedTasksLabel = useMemo(() => {
    const { total, completed, running, pending, failed } = pipelineLoadedTaskStats;
    if (total <= 0 && running + pending + failed + completed === 0) {
      return '0 tasks in loaded rows';
    }
    const bits: string[] = [`${total} tasks in loaded rows`];
    const sub: string[] = [];
    if (running) sub.push(`${running} running`);
    if (pending) sub.push(`${pending} pending`);
    if (completed) sub.push(`${completed} done`);
    if (failed) sub.push(`${failed} failed`);
    if (sub.length) bits.push(`(${sub.join(' · ')})`);
    return bits.join(' ');
  }, [pipelineLoadedTaskStats]);

  /** Row order in the full loaded list (for snapshot tail hint vs live API prefix). */
  const productRowIndex = useMemo(() => {
    const m = new Map<string, number>();
    for (let i = 0; i < products.length; i++) {
      const id = products[i]?.id;
      if (id != null) m.set(String(id), i);
    }
    return m;
  }, [products]);

  return (
    <motion.div className="space-y-4">
      <PipelineOnboardingCoach />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Pipeline Monitor</h2>
          {loadingMore && totalProducts > 0 && (
            <div className="mt-2 space-y-1.5" aria-live="polite" aria-busy="true">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400/95">
                <span
                  className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/80 animate-pulse"
                  aria-hidden
                />
                <span>
                  Updating from server… {products.length} / {totalProducts} rows (
                  <span className="tabular-nums">{catalogHydrationPercent}%</span> of catalog loaded)
                </span>
                <span className="text-slate-500 hidden sm:inline">· {pipelineLoadedTasksLabel}</span>
              </div>
              <div
                className="max-w-md h-1.5 overflow-hidden rounded-full bg-white/10"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={catalogHydrationPercent}
                aria-label="Catalog rows loaded"
              >
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500/90 to-teal-500/80 transition-[width] duration-300 ease-out"
                  style={{ width: `${catalogHydrationPercent}%` }}
                />
              </div>
            </div>
          )}
          {!loadingMore && totalProducts > 0 && products.length >= totalProducts && (
            <p className="text-xs text-gray-500 mt-1">All {totalProducts} products loaded in this view</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect
            value={pipelineSort}
            onChange={(e) => setPipelineSort(e.target.value as 'newest' | 'shipped_first')}
            className="px-3 py-1.5 min-w-[11rem]"
            title="Server-side sort for the whole catalog"
          >
            <option value="shipped_first">Sort: shipped first</option>
            <option value="newest">Sort: newest first</option>
          </FilterSelect>
          <Layers className="w-4 h-4 text-gray-500 hidden sm:block" />
          <FilterSelect
            value={activeCategory}
            onChange={(e) => setActiveCategory(e.target.value)}
            className="px-3 py-1.5"
          >
            <option value="all">All Categories ({totalProducts || products.length})</option>
            {PIPELINE_CATEGORY_FILTER_ORDER.map((catId) => (
              <option key={catId} value={catId}>
                {CATEGORY_LABELS[catId] || catId} (
                {pipelineCategoryCountsReady ? `${pipelineCategoryCounts[catId] ?? 0}${pipelineCategoryCountsPartial ? '+' : ''}` : '—'})
              </option>
            ))}
          </FilterSelect>
        </div>
      </div>

      {catalogSummary && catalogSummary.total_products > 0 && (
        <GlassCard className="p-4 border border-cyan-500/20 bg-cyan-500/[0.04]">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Store className="w-4 h-4 text-cyan-400" />
                Catalog vs first rows
              </h3>
              <p className="text-xs text-gray-400 mt-1 max-w-3xl">
                The UI restores the <strong className="text-gray-300">last catalog snapshot from this browser</strong>{' '}
                instantly, then revalidates in <strong className="text-gray-300">light mode</strong>: first{' '}
                <strong className="text-gray-300">{CATALOG_FIRST_FETCH}</strong> row(s) for a fast first paint, then batches of{' '}
                <strong className="text-gray-300">{CATALOG_BACKGROUND_CHUNK}</strong> (no eager per-row spec/marketing disk
                scan). Rows not yet refreshed this session look <strong className="text-gray-300">slightly muted</strong>{' '}
                until live data arrives. Default sort is{' '}
                <strong className="text-gray-300">shipped first</strong> so finished builds are not buried under new ideas. Switch
                to <strong className="text-gray-300">newest first</strong> for a strict time line, or use filters (
                <strong className="text-gray-300">State</strong>, <strong className="text-gray-300">Storefront</strong>
                ). Public storefront totals use the <strong className="text-gray-300">Dashboard</strong> tab.
              </p>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs shrink-0 min-w-[min(100%,28rem)]">
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500">In catalog</dt>
                <dd className="text-lg font-semibold text-white tabular-nums">{catalogSummary.total_products}</dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500">Shipped state</dt>
                <dd className="text-lg font-semibold text-emerald-300 tabular-nums">{catalogSummary.shipped_products}</dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500" title="Products that would appear on the public storefront grid (same rules as /api/products).">
                  Public storefront
                </dt>
                <dd className="text-lg font-semibold text-cyan-300 tabular-nums">
                  {typeof catalogSummary.storefront_listable_products === 'number'
                    ? catalogSummary.storefront_listable_products
                    : '—'}
                </dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500">Needs rework</dt>
                <dd className="text-lg font-semibold text-amber-300 tabular-nums">{catalogSummary.failed_products}</dd>
              </div>
            </dl>
          </div>
        </GlassCard>
      )}

      {catalogNotice && !loading && (
        <GlassCard className="p-3 mb-2 border border-sky-500/20 bg-sky-950/20">
          <div className="flex items-start justify-between gap-3 text-sm text-sky-100/90">
            <p className="min-w-0 leading-relaxed">{catalogNotice}</p>
            <button
              type="button"
              className="shrink-0 rounded-md p-1 text-sky-200/80 hover:bg-white/10 hover:text-white"
              aria-label="Dismiss notice"
              onClick={() => setCatalogNotice(null)}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </GlassCard>
      )}

      {catalogLoadError && !loading && (
        <GlassCard className="p-4 border border-white/10 bg-white/[0.04] mb-2">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="flex gap-3 text-sm min-w-0">
              <AlertTriangle className="w-5 h-5 shrink-0 text-amber-400/90 mt-0.5" />
              <div className="min-w-0">
                <p className="font-medium text-white">Catalog did not finish loading</p>
                <p className="text-xs text-gray-400 mt-1 break-words">
                  The UI already retried automatically (fast path, then full). If this persists, use Retry — it is
                  usually a temporary API or proxy issue, not an empty pipeline.
                </p>
                <p className="text-xs text-gray-500 mt-2 font-mono break-all">{catalogLoadError}</p>
              </div>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="shrink-0 self-start"
              onClick={() => reloadCatalog()}
            >
              <RefreshCw className="w-4 h-4 mr-1.5 inline" aria-hidden />
              Retry catalog
            </Button>
          </div>
        </GlassCard>
      )}

      <FilterControlsPanel
        onReset={() => {
          setProductSearch('');
          setStateFilter('all');
          setStorefrontFilter('all');
          setActiveCategory('all');
          setCreatedFrom('');
          setCreatedTo('');
        }}
        summary={
          loading && products.length === 0
            ? 'Waiting for the first catalog response (no local snapshot for this sort — see note above the progress bar).'
            : `Showing ${filteredProducts.length} of ${products.length} loaded (${totalProducts || products.length} in catalog)`
        }
        gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-2"
      >
        <Input
          value={productSearch}
          onChange={(e) => setProductSearch(e.target.value)}
          placeholder="Search by name, id, description, follow-up..."
        />
        <FilterSelect
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="px-3 py-2"
        >
          <option value="all">All states</option>
          {stateFilterOptions.map((st) => (
            <option key={st} value={st}>
              {getStateLabel(st)}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect
          value={storefrontFilter}
          onChange={(e) => setStorefrontFilter(e.target.value as 'all' | 'listed' | 'not_listed')}
          className="px-3 py-2"
        >
          <option value="all">Storefront: all</option>
          <option value="listed">Storefront: listed</option>
          <option value="not_listed">Storefront: not listed</option>
        </FilterSelect>
        <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
          <span>Created from (local day)</span>
          <input
            type="date"
            value={createdFrom}
            onChange={(e) => setCreatedFrom(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
          <span>Created to (local day)</span>
          <input
            type="date"
            value={createdTo}
            onChange={(e) => setCreatedTo(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
          />
        </label>
      </FilterControlsPanel>
      {loading ? (
        <div className="space-y-3 py-6">
          <div className="flex flex-col items-center justify-center gap-2 text-sm text-gray-400">
            <div className="flex items-center gap-2">
              <div className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-indigo-500/30 border-t-indigo-500" />
              Fetching first catalog page…
            </div>
            {catalogFirstPageFetch && (
              <div className="text-[11px] text-gray-500 text-center max-w-lg px-2 space-y-1">
                <p>
                  <span className="text-gray-400">Server request</span>{' '}
                  <span className="tabular-nums text-indigo-200/90">
                    {catalogFirstPageFetch.attempt + 1} / {catalogFirstPageFetch.maxAttempts}
                  </span>
                  {' — '}
                  each number is a real HTTP call; if the API is slow or returns an error, the client retries with
                  backoff (this is not a broken connection).
                </p>
                {catalogFirstPageFetch.lastError ? (
                  <p className="text-amber-200/85 break-words">
                    Last error:{' '}
                    {catalogFirstPageFetch.lastError.length > 160
                      ? `${catalogFirstPageFetch.lastError.slice(0, 160)}…`
                      : catalogFirstPageFetch.lastError}
                  </p>
                ) : null}
                {catalogFirstPageFetch.backoffMs != null && catalogFirstPageFetch.backoffMs > 0 ? (
                  <p className="text-slate-500">
                    Next attempt in ~{(catalogFirstPageFetch.backoffMs / 1000).toFixed(1)}s
                  </p>
                ) : null}
                <p className="text-slate-500">
                  <span className="text-gray-400">Browser snapshot:</span> none for this sort yet — after the first
                  successful load the Pipeline Monitor saves a slim copy in <code className="text-[10px]">localStorage</code>{' '}
                  so the next visit can paint cached rows immediately while refreshing in the background.
                </p>
              </div>
            )}
            <p className="text-[11px] text-gray-500 text-center max-w-md px-2">
              Row-level task counts appear once the first batch returns; the header then shows{' '}
              <span className="tabular-nums">N / total</span> and the bar below tracks catalog hydration (not this
              connection phase).
            </p>
          </div>
          {catalogFirstPageFetch && (
            <div className="max-w-md mx-auto px-2 space-y-1.5">
              <div className="flex justify-between text-[10px] text-gray-500">
                <span>Connection phase</span>
                <span className="tabular-nums">{firstCatalogPageProgressPct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={firstCatalogPageProgressPct}>
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-[width] duration-300 ease-out"
                  style={{ width: `${firstCatalogPageProgressPct}%` }}
                />
              </div>
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, si) => (
              <div
                key={`sk-${si}`}
                className="h-28 animate-pulse rounded-xl border border-white/5 bg-white/[0.04]"
              />
            ))}
          </div>
        </div>
      ) : filteredProducts.length === 0 ? (
        <div className="text-center py-12">
          <Activity className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-500">
            {catalogLoadError && products.length === 0
              ? 'Nothing loaded yet — tap “Retry catalog” above, or open the tab again in a few seconds.'
              : activeCategory !== 'all'
                ? `No products in "${CATEGORY_LABELS[activeCategory] || activeCategory}" category.`
                : stateFilter !== 'all' || storefrontFilter !== 'all' || productSearch.trim()
                  ? 'No products match the current filters or search.'
                  : 'No products in the pipeline catalog yet.'}
          </p>
        </div>
      ) : (
        <>
        {filteredProducts.map((product, i) => {
          const taskCounts = product.task_counts || {};
          const totalTasks = taskCounts.total || 0;
          const completedTasks = taskCounts.completed || 0;
          const progress = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
          const isExpanded = expandedProduct === product.id;
          const tasks = product.tasks || [];
          const productTitle = product.spec?.product_name || product.idea || product.id;
          const catId = bucketPipelineProductForCategoryFilter(product as Record<string, unknown>);
          const rowOrder = productRowIndex.get(String(product.id)) ?? 0;
          const isSnapshotTail =
            loadingMore && catalogLiveRowCount > 0 && rowOrder >= catalogLiveRowCount;
          
          return (
            <motion.div
              key={product.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: isSnapshotTail ? 0.92 : 1, y: 0 }}
              transition={{
                delay: filteredProducts.length > 40 ? 0 : Math.min(i, 10) * 0.018,
                opacity: { duration: 0.35 },
              }}
            >
              <GlassCard>
                <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className={`shrink-0 text-[10px] font-medium px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[catId] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                      {CATEGORY_LABELS[catId] || catId}
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-white font-medium">
                        {product.spec?.product_name || product.idea || product.id}
                      </h3>
                      <p className="text-xs text-gray-500 font-mono mt-0.5">{product.id}</p>
                      {(() => {
                        const raw = Number(product?.created_at) || 0;
                        const sec = raw > 1e12 ? raw / 1000 : raw;
                        if (!sec) return null;
                        return (
                          <p className="text-[11px] text-gray-500 mt-0.5">
                            Created <span className="text-gray-400">{formatDate(sec)}</span>
                          </p>
                        );
                      })()}
                      {(product.spec?.description || (product.idea && product.idea !== productTitle)) && (
                        <p className="text-sm text-gray-400 mt-1.5 leading-relaxed">
                          {product.spec?.description || product.idea}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
                    <Badge variant={product.production_mode ? 'warning' : 'info'}>
                      {product.production_mode ? 'production' : 'prototype'}
                    </Badge>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => loadSpec(product.id)}
                    >
                      <FileText className="w-3.5 h-3.5 mr-1" />
                      Spec
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => loadDeveloperHandoff(product.id)}
                      title="What the Developer agent receives (spec handoff quality)"
                    >
                      <ClipboardList className="w-3.5 h-3.5 mr-1" />
                      Dev handoff
                    </Button>
                    {String(product.state || '').toUpperCase() === 'FAILED' ? (
                      <span title="Pipeline paused — use Send to rework below">
                        <Badge variant="error">{getStateLabel(product.state)}</Badge>
                      </span>
                    ) : (
                      <Badge
                        variant={
                          product.state === 'COMPLETED' || product.state === 'completed'
                            ? 'success'
                            : String(product.state || '').toUpperCase() === 'HUMAN_REVIEW_PENDING'
                              ? 'warning'
                              : 'info'
                        }
                      >
                        {getStateLabel(product.state)}
                      </Badge>
                    )}
                  </div>
                </div>

                {/* ── Per-Product Economics Badges ─────────────────── */}
                {product.economics && (
                  <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px]">
                    {/* LLM Cost */}
                    <span
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                        (product.economics.llm_cost_usd || 0) > 5
                          ? 'bg-red-500/15 text-red-300 border border-red-500/20'
                          : (product.economics.llm_cost_usd || 0) > 1
                            ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                            : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                      }`}
                      title={`LLM API cost: $${(product.economics.llm_cost_usd || 0).toFixed(4)} · ${product.economics.llm_call_count || 0} calls · ${(product.economics.llm_total_tokens || 0).toLocaleString()} tokens`}
                    >
                      <span className="text-[10px]">💰</span>
                      ${(product.economics.llm_cost_usd || 0).toFixed(2)}
                    </span>

                    {/* Quality Score */}
                    {product.economics.quality_score != null && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                          product.economics.quality_score >= 4
                            ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                            : product.economics.quality_score >= 3
                              ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                              : 'bg-red-500/15 text-red-300 border border-red-500/20'
                        }`}
                        title="Human quality score (1–5)"
                      >
                        <span className="text-[10px]">📊</span>
                        {product.economics.quality_score}/5
                      </span>
                    )}

                    {/* ROI Band */}
                    <span
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                        product.economics.roi_band === 'green'
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                          : product.economics.roi_band === 'amber'
                            ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                            : 'bg-red-500/15 text-red-300 border border-red-500/20'
                      }`}
                      title={
                        product.economics.roi_band === 'green'
                          ? 'Low cost or high quality — good economics'
                          : product.economics.roi_band === 'amber'
                            ? 'Moderate cost-to-quality ratio'
                            : 'High cost with low quality — needs attention'
                      }
                    >
                      {product.economics.roi_band === 'green' ? '🟢' : product.economics.roi_band === 'amber' ? '🟡' : '🔴'}
                      {' ROI'}
                    </span>

                    {/* Agent breakdown tooltip */}
                    {product.economics.llm_agent_breakdown &&
                      Object.keys(product.economics.llm_agent_breakdown).length > 0 && (
                        <span
                          className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium bg-white/5 text-gray-400 border border-white/10 cursor-help"
                          title={Object.entries(product.economics.llm_agent_breakdown)
                            .map(
                              ([agent, s]: [string, any]) =>
                                `${agent}: $${(s.cost_usd || 0).toFixed(4)} (${s.calls} calls, ${(s.tokens || 0).toLocaleString()} tok)`,
                            )
                            .join(' · ')}
                        >
                          <span className="text-[10px]">🔍</span>
                          {Object.keys(product.economics.llm_agent_breakdown).length} agents
                        </span>
                      )}
                  </div>
                )}

                {product.pulse && (
                  <ProductPulse pulse={product.pulse as ProductPulsePayload} />
                )}

                {String(product.state || '').toUpperCase() === 'FAILED' && (
                  <PipelineProductFailedPanel
                    productId={product.id}
                    productTitle={productTitle}
                    product={product as Record<string, unknown>}
                    onReopened={(patch) => mergeProductPatch(product.id, patch)}
                  />
                )}

                {String(product.state || '').toUpperCase() === 'HUMAN_REVIEW_PENDING' && (
                  <HumanReviewGatePanel product={product} onPatch={mergeProductPatch} />
                )}

                {(String(product.state || '').toUpperCase() === 'COMPLETED' ||
                  String(product.state || '').toUpperCase() === 'DEPLOYED_PRODUCTION') && (
                  <StorefrontFollowupPanel product={product} onPatch={mergeProductPatch} />
                )}

                {/* Pipeline Stage Flow Bar — always show full stage row (incl. Designer) even before tasks land in queue */}
                <div className="mb-4 overflow-x-auto">
                  <p className="text-[10px] text-gray-500 mb-2">
                    Click an agent tile, a colored link between stages, or a task circle below for full task details.
                  </p>
                  <div className="flex items-center min-w-max gap-0">
                    {(PIPELINE_STAGE_ORDER as readonly string[]).map((agentType, ai, arr) => {
                        const task = findTaskForStage(tasks, agentType);
                        const status = String(task?.status ?? 'pending');
                        /** Designer (UX) mirrors Architect — use fuchsia, not emerald, so it is not mistaken for a generic “green done” pipeline cell. */
                        const stageColors: Record<string, string> =
                          agentType === 'designer'
                            ? {
                                completed:
                                  'bg-fuchsia-600 border-fuchsia-400 text-white',
                                running:
                                  'bg-fuchsia-500 border-fuchsia-300 text-white animate-pulse',
                                failed: 'bg-red-500 border-red-400 text-red-900',
                                pending: 'bg-white/5 border-white/10 text-gray-500',
                              }
                            : {
                                completed:
                                  'bg-emerald-500 border-emerald-400 text-emerald-900',
                                running:
                                  'bg-amber-500 border-amber-400 text-amber-900 animate-pulse',
                                failed: 'bg-red-500 border-red-400 text-red-900',
                                pending: 'bg-white/5 border-white/10 text-gray-500',
                              };
                        const stageIcons: Record<string, string> = {
                          analyst: '🔍', pm: '📋', methodologist: '🧭',
                          architect: '🏗️', designer: '🎨', developer: '💻', qa: '🧪',
                          security: '🛡️', devops: '🚀', marketing: '📢',
                          sales: '💰',
                        };
                        const productTitle =
                          product.spec?.product_name || product.idea || product.id;
                        return (
                          <React.Fragment key={agentType}>
                            <div className="flex flex-col items-center gap-1 shrink-0 min-w-[2.5rem]">
                              <button
                                type="button"
                                title={
                                  agentType === 'designer'
                                    ? 'Designer (UX): status follows Architect — opens Architect task details'
                                    : agentType === 'methodologist'
                                      ? 'Methodologist: domain methodology snapshot after marketing; backlog for Architect'
                                      : 'Task details for this agent stage'
                                }
                                onClick={() =>
                                  openTaskDetailModal(product.id, productTitle, agentType, task ? { ...task } : null)
                                }
                                className="flex flex-col items-center gap-1 rounded-xl p-0.5 -m-0.5 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-colors cursor-pointer group"
                              >
                                <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs border-2 transition-all group-hover:scale-105 ${stageColors[status] || 'bg-white/5 border-white/10 text-gray-500'}`}>
                                  {stageIcons[agentType] || '⚙️'}
                                </div>
                                <span className={`text-[10px] font-medium ${
                                  status === 'completed'
                                    ? agentType === 'designer'
                                      ? 'text-fuchsia-400'
                                      : 'text-emerald-400'
                                    : status === 'running'
                                      ? agentType === 'designer'
                                        ? 'text-fuchsia-300'
                                        : 'text-amber-400'
                                      : status === 'failed'
                                        ? 'text-red-400'
                                        : 'text-gray-600'
                                }`}>
                                  {agentType === 'analyst'
                                    ? 'Anl'
                                    : agentType === 'marketing'
                                      ? 'Mkt'
                                      : agentType === 'designer'
                                        ? 'UX'
                                        : agentType === 'methodologist'
                                          ? 'Mth'
                                          : agentType === 'devops'
                                            ? 'Ops'
                                            : agentType.charAt(0).toUpperCase() + agentType.slice(1, 3)}
                                </span>
                              </button>
                            </div>
                            {ai < arr.length - 1 && (
                              <div className={`h-0.5 w-6 mx-1 rounded-full mt-[-18px] ${
                                status === 'completed'
                                  ? agentType === 'designer'
                                    ? 'bg-fuchsia-500/50'
                                    : 'bg-emerald-500/50'
                                  : status === 'running'
                                    ? agentType === 'designer'
                                      ? 'bg-fuchsia-500/30'
                                      : 'bg-amber-500/30'
                                    : 'bg-white/5'
                              }`} />
                            )}
                          </React.Fragment>
                        );
                      })}
                  </div>
                </div>

                {/* Progress bar */}
                {totalTasks > 0 && (
                  <div className="mb-3">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Progress</span>
                      <span>{completedTasks}/{totalTasks} tasks ({progress}%)</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  </div>
                )}
                
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatRelativeTime(product.created_at)}
                    </span>
                    <span>{totalTasks} tasks ({completedTasks} done)</span>
                    {taskCounts.running > 0 && (
                      <span className="text-amber-400">{taskCounts.running} running...</span>
                    )}
                    {taskCounts.failed > 0 && (
                      <span className="text-amber-400">{taskCounts.failed} rework</span>
                    )}
                  </div>
                  {tasks.length > 0 && (
                    <button
                      onClick={() => setExpandedProduct(isExpanded ? null : product.id)}
                      className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      {isExpanded ? 'Hide Tasks' : 'Show Tasks'}
                      <ChevronRight className={`w-3.5 h-3.5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                    </button>
                  )}
                </div>

                {/* Expandable Task Timeline */}
                {isExpanded && tasks.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-4 border-t border-white/5 pt-4"
                  >
                    <div className="space-y-0">
                      {tasks.map((task: any, ti: number) => {
                        const taskStatus = task.status || 'pending';
                        const statusColors: Record<string, string> = {
                          completed: 'border-emerald-500 bg-emerald-500/20',
                          running: 'border-amber-500 bg-amber-500/20',
                          failed: 'border-red-500 bg-red-500/20',
                          pending: 'border-gray-600 bg-gray-600/20',
                        };
                        const dotColors: Record<string, string> = {
                          completed: 'bg-emerald-500 shadow-emerald-500/50',
                          running: 'bg-amber-500 animate-pulse shadow-amber-500/50',
                          failed: 'bg-red-500 shadow-red-500/50',
                          pending: 'bg-gray-600',
                        };
                        
                        return (
                          <div key={task.id || ti} className="flex gap-3 relative pb-4 last:pb-0">
                            {/* Timeline connector line */}
                            {ti < tasks.length - 1 && (
                              <div className="absolute left-[15px] top-[30px] bottom-0 w-px bg-white/5" />
                            )}
                            
                            {/* Status dot — click opens same detail modal as the stage bar */}
                            <div className="flex-shrink-0 mt-1.5">
                              <button
                                type="button"
                                title="Open full task details"
                                onClick={() =>
                                  openTaskDetailModal(
                                    product.id,
                                    product.spec?.product_name || product.idea || product.id,
                                    String(task.agent_type || ''),
                                    task as Record<string, unknown>
                                  )
                                }
                                className={`w-[30px] h-[30px] rounded-full flex items-center justify-center border transition-transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 ${statusColors[taskStatus] || 'border-gray-600 bg-gray-600/20'}`}
                              >
                                <span className="text-xs">{pipelineAgentEmoji(task.agent_type)}</span>
                              </button>
                            </div>

                            {/* Task details */}
                            <div className="flex-1 min-w-0 pt-0.5">
                              <div className="flex items-center justify-between mb-0.5">
                                <span className="text-sm font-medium text-white capitalize">
                                  {task.agent_type?.replace(/_/g, ' ') || 'Unknown'}
                                </span>
                                <div className="flex items-center gap-2">
                                  <span className={`text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded ${
                                    taskStatus === 'completed' ? 'text-emerald-400 bg-emerald-500/10' :
                                    taskStatus === 'running' ? 'text-amber-400 bg-amber-500/10' :
                                    taskStatus === 'failed' ? 'text-red-400 bg-red-500/10' :
                                    'text-gray-500 bg-gray-500/10'
                                  }`}>
                                    {taskStatus}
                                  </span>
                                </div>
                              </div>
                              
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500">
                                {task.started_at && (
                                  <span>Started: {new Date(task.started_at * 1000).toLocaleTimeString()}</span>
                                )}
                                {task.completed_at && (
                                  <span>Completed: {new Date(task.completed_at * 1000).toLocaleTimeString()}</span>
                                )}
                                {task.started_at && task.completed_at && (
                                  <span>Duration: {formatTaskDuration(task.started_at, task.completed_at)}</span>
                                )}
                                {task.metrics?.llm_time_ms && (
                                  <span>LLM: {(task.metrics.llm_time_ms / 1000).toFixed(1)}s</span>
                                )}
                              </div>

                              {/* Error message for failed tasks */}
                              {task.error && (
                                <div className="mt-1 text-[11px] text-red-400 bg-red-500/5 rounded px-2 py-1 border border-red-500/10">
                                  {task.error}
                                </div>
                              )}

                              {/* State info */}
                              {task.state && (
                                <div className="mt-0.5 text-[10px] text-gray-600 font-mono">
                                  State: {task.state}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </GlassCard>
            </motion.div>
          );
        })}
        {loadingMore && filteredProducts.length > 0 && (
          <div className="py-4 flex flex-col items-center justify-center px-2 gap-2">
            <p className="text-[11px] text-slate-500 text-center max-w-md flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
              <RefreshCw className="w-3 h-3 shrink-0 animate-spin text-slate-500" aria-hidden />
              <span>
                Syncing catalog… {products.length} / {totalProducts} (
                <span className="tabular-nums">{catalogHydrationPercent}%</span>)
              </span>
            </p>
            <div
              className="w-full max-w-md h-1.5 overflow-hidden rounded-full bg-white/10"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={catalogHydrationPercent}
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-500/90 to-teal-500/80 transition-[width] duration-300 ease-out"
                style={{ width: `${catalogHydrationPercent}%` }}
              />
            </div>
          </div>
        )}
        {!loadingMore && products.length > 0 && products.length >= totalProducts && (
          <p className="text-center text-xs text-gray-600 py-2">
            End of list ({totalProducts || products.length} products)
          </p>
        )}
        </>
      )}

      {/* Spec Viewer Modal */}
      <Modal
        isOpen={specModalProduct !== null}
        onClose={closeSpecModal}
        title="Product Specification"
        size="xl"
      >
        {specLoading ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-gray-500">Loading specification...</p>
          </div>
        ) : specData ? (
          <div className="space-y-6 max-h-[70vh] overflow-y-auto">
            {specData.product_name && (
              <div>
                <h3 className="text-sm text-gray-500 mb-1">Product Name</h3>
                <p className="text-white font-medium text-lg">{specData.product_name}</p>
              </div>
            )}
            {specData.description && (
              <div>
                <h3 className="text-sm text-gray-500 mb-1">Description</h3>
                <p className="text-gray-300 text-sm whitespace-pre-wrap">{specData.description}</p>
              </div>
            )}
            {specData.core_features && specData.core_features.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">Core Features</h3>
                <ul className="space-y-1.5">
                  {specData.core_features.map((feature: string, fi: number) => (
                    <li key={fi} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-indigo-400 mt-0.5">•</span>
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {specData.user_stories && specData.user_stories.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">User Stories</h3>
                <ul className="space-y-1.5">
                  {specData.user_stories.map((story: string, si: number) => (
                    <li key={si} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-emerald-400 mt-0.5">•</span>
                      {story}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {specData.technical_risks && specData.technical_risks.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">Technical Risks</h3>
                <ul className="space-y-1.5">
                  {specData.technical_risks.map((risk: string, ri: number) => (
                    <li key={ri} className="flex items-start gap-2 text-sm text-amber-300">
                      <span className="text-amber-400 mt-0.5">⚠</span>
                      {risk}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!specData.product_name && !specData.description && !specData.core_features && (
              <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono bg-black/30 p-4 rounded-lg max-h-[50vh] overflow-y-auto">
                {JSON.stringify(specData, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No specification found for this product.</p>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={handoffModalProduct !== null}
        onClose={closeHandoffModal}
        title="Developer handoff (inputs to code agent)"
        size="xl"
      >
        {handoffLoading ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-gray-500">Loading developer inputs...</p>
          </div>
        ) : handoffData ? (
          <div className="space-y-4 max-h-[72vh] overflow-y-auto pr-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-gray-500">Product</span>
              <code className="text-[11px] text-cyan-300 bg-black/30 px-2 py-0.5 rounded">{handoffData.product_id}</code>
              <Badge
                variant={
                  handoffData.material_summary.quality_band === 'weak'
                    ? 'error'
                    : handoffData.material_summary.quality_band === 'thin'
                      ? 'warning'
                      : 'success'
                }
              >
                Material: {handoffData.material_summary.quality_band}
              </Badge>
              <span className="text-xs text-gray-500">
                delivery_mode={handoffData.delivery_mode}
                {handoffData.delivery_profile ? ` · profile=${handoffData.delivery_profile}` : ''}
              </span>
            </div>
            {handoffData.material_summary.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 space-y-1.5">
                <p className="text-xs font-medium text-amber-200">Warnings</p>
                <ul className="list-disc list-inside text-xs text-amber-100/90 space-y-1">
                  {handoffData.material_summary.warnings.map((w, wi) => (
                    <li key={wi}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-2 text-[11px] text-gray-400">
              {Object.entries(handoffData.material_summary.stats || {}).map(([k, v]) => (
                <span key={k} className="rounded-md bg-white/5 border border-white/10 px-2 py-0.5 font-mono">
                  {k}: {v}
                </span>
              ))}
            </div>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">Admin instructions</summary>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans px-3 pb-3 max-h-48 overflow-y-auto">
                {handoffData.admin_instructions?.trim() || '(empty)'}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">
                Analyst → developer brief (developer_investigation_brief)
              </summary>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans px-3 pb-3 max-h-56 overflow-y-auto">
                {handoffData.analyst_brief_for_developer?.trim() ||
                  '(empty — for web_app this block is omitted from the developer prompt)'}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">Specification (JSON)</summary>
              <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {safeJson(handoffData.specification)}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">Architecture (JSON)</summary>
              <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {safeJson(handoffData.architecture)}
              </pre>
            </details>
          </div>
        ) : (
          <div className="text-center py-12">
            <ClipboardList className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">Could not load developer handoff for this product.</p>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={taskStageModal !== null}
        onClose={() => setTaskStageModal(null)}
        title={
          taskStageModal
            ? `${STAGE_AGENT_TITLE[taskStageModal.agentType] || taskStageModal.agentType} — pipeline task`
            : ''
        }
        size="xl"
        className="max-w-2xl max-h-[90vh] flex flex-col"
      >
        {taskStageModal && (
          <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1 text-sm">
            <div className="rounded-xl bg-white/5 border border-white/10 p-3">
              <p className="text-xs text-gray-500 mb-0.5">Product</p>
              <p className="text-white font-medium">{taskStageModal.productName}</p>
              <p className="text-[11px] text-gray-500 font-mono mt-1">{taskStageModal.productId}</p>
            </div>

            {taskStageModal.agentType === 'designer' && taskStageModal.task && (
              <p className="text-xs text-fuchsia-200/95 bg-fuchsia-500/10 border border-fuchsia-500/25 rounded-lg px-3 py-2 leading-relaxed">
                <strong className="text-fuchsia-100">Designer</strong> is a pipeline visualization: UX direction is
                authored with the <strong className="text-fuchsia-100">Architect</strong> output (
                <code className="text-cyan-300/90">ui_experience</code>
                ). The task record below is the <strong className="text-fuchsia-100">Architect</strong> task.
              </p>
            )}

            {!taskStageModal.task && (
              <p className="text-gray-400 text-sm leading-relaxed">
                No queued task for this stage yet: the pipeline has not reached it, the task was not created, or data
                is still loading. Expand <span className="text-indigo-300">Show Tasks</span> on the product card below for the full task list.
              </p>
            )}

            {taskStageModal.task && (() => {
              const t = taskStageModal.task;
              const st = (t.status as string) || 'unknown';
              const sc = toUnixSeconds(t.started_at);
              const ec = toUnixSeconds(t.completed_at);
              const cc = toUnixSeconds(t.created_at);
              const durMain =
                sc !== undefined && ec !== undefined ? formatTaskDuration(sc, ec) : '';
              const durQueue =
                cc !== undefined && sc !== undefined ? formatTaskDuration(cc, sc) : '';
              const out = t.output_data as Record<string, unknown> | undefined;
              const inp = t.input_data as Record<string, unknown> | undefined;
              const criticFeedback =
                (inp && typeof inp.critic_feedback === 'object' && inp.critic_feedback !== null
                  ? (inp.critic_feedback as Record<string, unknown>)
                  : undefined) ||
                (out && typeof out.critic_feedback === 'object' && out.critic_feedback !== null
                  ? (out.critic_feedback as Record<string, unknown>)
                  : undefined);
              const metrics =
                (t.metrics as Record<string, unknown> | undefined) ||
                (out && typeof out.metrics === 'object' && out.metrics !== null
                  ? (out.metrics as Record<string, unknown>)
                  : undefined);

              return (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-gray-500">Task ID</span>
                    <code className="text-[11px] text-cyan-300 bg-black/30 px-2 py-0.5 rounded">{String(t.id ?? '—')}</code>
                    <span
                      className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${
                        st === 'completed'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : st === 'running'
                            ? 'bg-amber-500/15 text-amber-300'
                            : st === 'failed'
                              ? 'bg-red-500/15 text-red-400'
                              : 'bg-white/10 text-gray-400'
                      }`}
                    >
                      {st}
                    </span>
                  </div>

                  {t.state != null && (
                    <p className="text-xs text-gray-500">
                      Target pipeline state:{' '}
                      <span className="text-gray-300 font-mono">{String(t.state)}</span>
                    </p>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">Created</p>
                      <p className="text-gray-200">{formatTaskWhen(t.created_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">Started</p>
                      <p className="text-gray-200">{formatTaskWhen(t.started_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">Completed</p>
                      <p className="text-gray-200">{formatTaskWhen(t.completed_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">Durations</p>
                      <p className="text-gray-200">
                        {durMain ? (
                          <span>
                            Work: <strong className="text-white">{durMain}</strong>
                          </span>
                        ) : (
                          <span className="text-gray-500">Work: —</span>
                        )}
                        {durQueue ? (
                          <span className="block mt-0.5">
                            In queue: <strong className="text-gray-300">{durQueue}</strong>
                          </span>
                        ) : null}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-400">
                    {t.timeout_sec != null && (
                      <span>
                        Timeout: <span className="text-gray-200">{String(t.timeout_sec)}s</span>
                      </span>
                    )}
                    {t.priority != null && (
                      <span>
                        Priority: <span className="text-gray-200">{String(t.priority)}</span>
                      </span>
                    )}
                    {(t.retry_count != null || t.max_retries != null) && (
                      <span>
                        Retries:{' '}
                        <span className="text-gray-200">
                          {String(t.retry_count ?? 0)} / {String(t.max_retries ?? '—')}
                        </span>
                      </span>
                    )}
                  </div>

                  {metrics && Object.keys(metrics).length > 0 && (
                    <details open className="rounded-lg border border-indigo-500/20 bg-indigo-500/5">
                      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-indigo-200">
                        Metrics
                      </summary>
                      <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 overflow-x-auto">
                        {safeJson(metrics, 32_000)}
                      </pre>
                    </details>
                  )}

                  {criticFeedback && (
                    <details open className="rounded-lg border border-amber-500/30 bg-amber-500/10">
                      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-amber-200">
                        Critic findings
                      </summary>
                      <pre className="text-[11px] text-amber-100/90 font-mono px-3 pb-3 overflow-x-auto whitespace-pre-wrap">
                        {safeJson(criticFeedback, 24_000)}
                      </pre>
                    </details>
                  )}

                  {t.error != null && String(t.error).trim() !== '' && (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300 whitespace-pre-wrap">
                      {String(t.error)}
                    </div>
                  )}

                  {inp && Object.keys(inp).length > 0 && (
                    <details className="rounded-lg border border-white/10 bg-black/20">
                      <summary className="cursor-pointer px-3 py-2 text-xs text-gray-400">
                        input_data
                      </summary>
                      <pre className="text-[11px] text-gray-500 font-mono px-3 pb-3 max-h-48 overflow-auto">
                        {safeJson(inp)}
                      </pre>
                    </details>
                  )}

                  {out && Object.keys(out).length > 0 && (
                    <details className="rounded-lg border border-white/10 bg-black/20">
                      <summary className="cursor-pointer px-3 py-2 text-xs text-gray-400">
                        output_data
                      </summary>
                      <pre className="text-[11px] text-gray-500 font-mono px-3 pb-3 max-h-64 overflow-auto">
                        {safeJson(out)}
                      </pre>
                    </details>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </Modal>
    </motion.div>
  );
}
