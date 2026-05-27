'use client';

import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, AlertTriangle, Layers, RefreshCw, Store, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { FilterControlsPanel, FilterSelect } from '@/components/admin/FilterControls';
import { getStateLabel } from '@/lib/utils';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { CATEGORY_LABELS } from './pipelineConstants';
import { PIPELINE_CATEGORY_FILTER_ORDER } from '@/lib/pipelineCategoryBucket';
import { usePipelineCatalog } from '@/hooks/admin/usePipelineCatalog';
import { usePipelineFilters } from '@/hooks/admin/usePipelineFilters';
import { usePipelineModals } from '@/hooks/admin/usePipelineModals';
import { usePipelineProductPulses } from '@/hooks/admin/usePipelineProductPulses';
import { PipelineOnboardingCoach } from '@/components/admin/pipeline/PipelineOnboardingCoach';
import { PipelineTabModals } from '@/components/admin/pipeline/PipelineTabModals';
import { PipelineProductList } from '@/components/admin/pipeline/PipelineProductList';
import { PipelineProductVitalsTable } from '@/components/admin/pipeline/PipelineProductVitalsTable';

export function PipelineTab({ locale }: { locale: AdminLocale }) {
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
  } = filters;

  const modals = usePipelineModals();
  const {
    expandedProduct,
    setExpandedProduct,
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
      return t(locale, 'pipeline.loadedTasks.none');
    }
    const sub: string[] = [];
    if (running) sub.push(tVars(locale, 'pipeline.task.running', { n: running }));
    if (pending) sub.push(tVars(locale, 'pipeline.task.pending', { n: pending }));
    if (completed) sub.push(tVars(locale, 'pipeline.task.done', { n: completed }));
    if (failed) sub.push(tVars(locale, 'pipeline.task.failed', { n: failed }));
    return tVars(locale, 'pipeline.loadedTasks.line', {
      total,
      breakdown: sub.join(' · '),
    });
  }, [pipelineLoadedTaskStats, locale]);

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
      <PipelineOnboardingCoach locale={locale} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-white">{t(locale, 'pipeline.title')}</h2>
          {loadingMore && totalProducts > 0 && (
            <div className="mt-2 space-y-1.5" aria-live="polite" aria-busy="true">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400/95">
                <span
                  className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/80 animate-pulse"
                  aria-hidden
                />
                <span>
                  {t(locale, 'pipeline.updatingServer')}{' '}
                  {tVars(locale, 'pipeline.rowsFraction', { loaded: products.length, total: totalProducts })}
                  <span className="tabular-nums">
                    {tVars(locale, 'pipeline.ofCatalogLoaded', { pct: catalogHydrationPercent })}
                  </span>
                </span>
                <span className="text-slate-500 hidden sm:inline">· {pipelineLoadedTasksLabel}</span>
              </div>
              <div
                className="max-w-md h-1.5 overflow-hidden rounded-full bg-white/10"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={catalogHydrationPercent}
                aria-label={t(locale, 'pipeline.aria.catalogRowsLoaded')}
              >
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500/90 to-teal-500/80 transition-[width] duration-300 ease-out"
                  style={{ width: `${catalogHydrationPercent}%` }}
                />
              </div>
            </div>
          )}
          {!loadingMore && totalProducts > 0 && products.length >= totalProducts && (
            <p className="text-xs text-gray-500 mt-1">
              {tVars(locale, 'pipeline.allProductsLoaded', { total: totalProducts })}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect
            value={pipelineSort}
            onChange={(e) => setPipelineSort(e.target.value as 'newest' | 'shipped_first')}
            className="px-3 py-1.5 min-w-[11rem]"
            title={t(locale, 'pipeline.sortTooltip')}
          >
            <option value="shipped_first">{t(locale, 'pipeline.sortShippedFirst')}</option>
            <option value="newest">{t(locale, 'pipeline.sortNewestFirst')}</option>
          </FilterSelect>
          <Layers className="w-4 h-4 text-gray-500 hidden sm:block" />
          <FilterSelect
            value={activeCategory}
            onChange={(e) => setActiveCategory(e.target.value)}
            className="px-3 py-1.5"
          >
            <option value="all">
              {tVars(locale, 'pipeline.allCategories', { count: totalProducts || products.length })}
            </option>
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
                {t(locale, 'pipeline.catalogBannerTitle')}
              </h3>
              <p className="text-xs text-gray-400 mt-1 max-w-3xl">{t(locale, 'pipeline.catalogBannerBody')}</p>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs shrink-0 min-w-[min(100%,28rem)]">
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500">{t(locale, 'pipeline.stat.inCatalog')}</dt>
                <dd className="text-lg font-semibold text-white tabular-nums">{catalogSummary.total_products}</dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500" title={t(locale, 'pipeline.stat.shippedStateTooltip')}>
                  {t(locale, 'pipeline.stat.shippedState')}
                </dt>
                <dd className="text-lg font-semibold text-emerald-300 tabular-nums">{catalogSummary.shipped_products}</dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500" title={t(locale, 'pipeline.catalogPublicStoreTooltip')}>
                  {t(locale, 'pipeline.stat.publicStorefrontTitle')}
                </dt>
                <dd className="text-lg font-semibold text-cyan-300 tabular-nums">
                  {typeof catalogSummary.storefront_listable_products === 'number'
                    ? catalogSummary.storefront_listable_products
                    : '—'}
                </dd>
              </div>
              <div className="rounded-lg bg-black/25 px-3 py-2 border border-white/10">
                <dt className="text-gray-500">{t(locale, 'pipeline.stat.needsRework')}</dt>
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
              aria-label={t(locale, 'pipeline.dismissNotice')}
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
                <p className="font-medium text-white">{t(locale, 'pipeline.catalogLoadErrorTitle')}</p>
                <p className="text-xs text-gray-400 mt-1 break-words">{t(locale, 'pipeline.catalogLoadErrorBody')}</p>
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
              {t(locale, 'pipeline.retryCatalog')}
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
            ? t(locale, 'pipeline.filter.summaryWaitingFirst')
            : tVars(locale, 'pipeline.filter.summaryShowing', {
                shown: filteredProducts.length,
                loaded: products.length,
                catalog: totalProducts || products.length,
              })
        }
        gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-2"
      >
        <Input
          value={productSearch}
          onChange={(e) => setProductSearch(e.target.value)}
          placeholder={t(locale, 'pipeline.search.placeholder')}
        />
        <FilterSelect
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="px-3 py-2"
        >
          <option value="all">{t(locale, 'pipeline.filter.allStates')}</option>
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
          <option value="all">{t(locale, 'pipeline.filter.storefrontAll')}</option>
          <option value="listed">{t(locale, 'pipeline.filter.storefrontListed')}</option>
          <option value="not_listed">{t(locale, 'pipeline.filter.storefrontNotListed')}</option>
        </FilterSelect>
        <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
          <span>{t(locale, 'pipeline.filter.createdFrom')}</span>
          <input
            type="date"
            value={createdFrom}
            onChange={(e) => setCreatedFrom(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
          <span>{t(locale, 'pipeline.filter.createdTo')}</span>
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
              {t(locale, 'pipeline.loading.fetchingFirst')}
            </div>
            {catalogFirstPageFetch && (
              <div className="text-[11px] text-gray-500 text-center max-w-lg px-2 space-y-1">
                <p>
                  <span className="text-gray-400">{t(locale, 'pipeline.loading.serverRequest')}</span>{' '}
                  <span className="tabular-nums text-indigo-200/90">
                    {catalogFirstPageFetch.attempt + 1} / {catalogFirstPageFetch.maxAttempts}
                  </span>
                  {' — '}
                  {t(locale, 'pipeline.loading.retryExplainer')}
                </p>
                {catalogFirstPageFetch.lastError ? (
                  <p className="text-amber-200/85 break-words">
                    {t(locale, 'pipeline.loading.lastError')}{' '}
                    {catalogFirstPageFetch.lastError.length > 160
                      ? `${catalogFirstPageFetch.lastError.slice(0, 160)}…`
                      : catalogFirstPageFetch.lastError}
                  </p>
                ) : null}
                {catalogFirstPageFetch.backoffMs != null && catalogFirstPageFetch.backoffMs > 0 ? (
                  <p className="text-slate-500">
                    {tVars(locale, 'pipeline.loading.nextAttempt', {
                      sec: (catalogFirstPageFetch.backoffMs / 1000).toFixed(1),
                    })}
                  </p>
                ) : null}
                <p className="text-slate-500">
                  <span className="text-gray-400">{t(locale, 'pipeline.loading.browserSnapshotHint')}</span>{' '}
                  {t(locale, 'pipeline.loading.browserSnapshotTail')}
                </p>
              </div>
            )}
            <p className="text-[11px] text-gray-500 text-center max-w-md px-2">
              {t(locale, 'pipeline.loading.footerHint')}
            </p>
          </div>
          {catalogFirstPageFetch && (
            <div className="max-w-md mx-auto px-2 space-y-1.5">
              <div className="flex justify-between text-[10px] text-gray-500">
                <span>{t(locale, 'pipeline.loading.connectionPhase')}</span>
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
              ? t(locale, 'pipeline.empty.needRetry')
              : activeCategory !== 'all'
                ? tVars(locale, 'pipeline.empty.category', {
                    category: CATEGORY_LABELS[activeCategory] || activeCategory,
                  })
                : stateFilter !== 'all' || storefrontFilter !== 'all' || productSearch.trim()
                  ? t(locale, 'pipeline.empty.filtered')
                  : t(locale, 'pipeline.empty.catalog')}
          </p>
        </div>
      ) : (
        <>
        <PipelineProductVitalsTable products={filteredProducts} locale={locale} />
        <PipelineProductList
          locale={locale}
          filteredProducts={filteredProducts}
          productRowIndex={productRowIndex}
          loadingMore={loadingMore}
          catalogLiveRowCount={catalogLiveRowCount}
          productsLoaded={products.length}
          totalProducts={totalProducts}
          catalogHydrationPercent={catalogHydrationPercent}
          expandedProduct={expandedProduct}
          setExpandedProduct={setExpandedProduct}
          loadSpec={loadSpec}
          loadDeveloperHandoff={loadDeveloperHandoff}
          openTaskDetailModal={openTaskDetailModal}
          mergeProductPatch={mergeProductPatch}
        />
        </>
      )}

      <PipelineTabModals
        locale={locale}
        specModalProduct={specModalProduct}
        closeSpecModal={closeSpecModal}
        specLoading={specLoading}
        specData={specData}
        handoffModalProduct={handoffModalProduct}
        closeHandoffModal={closeHandoffModal}
        handoffLoading={handoffLoading}
        handoffData={handoffData}
        taskStageModal={taskStageModal}
        setTaskStageModal={setTaskStageModal}
      />
    </motion.div>
  );
}