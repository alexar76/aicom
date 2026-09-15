'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { PIPELINE_PRODUCT_STATES_FOR_FILTER } from '@/lib/pipelineStages';
import { localDateInputStartSeconds, localDateInputEndSeconds } from '@/lib/utils';
import {
  bucketPipelineProductForCategoryFilter,
  countPipelineProductsByCategory,
} from '@/lib/pipelineCategoryBucket';

export type DeliveryProfileFilter = 'all' | 'full_software' | 'marketing_landing' | 'landing_fast';
export type PipelineWorkFilter = 'all' | 'active' | 'paused' | 'focus';

export function usePipelineFilters(products: any[], totalProducts: number, loadingMore: boolean) {
  const searchParams = useSearchParams();
  const [activeCategory, setActiveCategory] = useState('all');
  const [productSearch, setProductSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('all');
  const [storefrontFilter, setStorefrontFilter] = useState<'all' | 'listed' | 'not_listed'>('all');
  const [deliveryProfileFilter, setDeliveryProfileFilter] = useState<DeliveryProfileFilter>('all');
  const [pipelineWorkFilter, setPipelineWorkFilter] = useState<PipelineWorkFilter>('all');
  const [repairRoundMin, setRepairRoundMin] = useState<'all' | '1' | '2' | '3'>('all');
  const [createdFrom, setCreatedFrom] = useState('');
  const [createdTo, setCreatedTo] = useState('');

  useEffect(() => {
    const q = searchParams.get('pipelineSearch')?.trim();
    if (q) setProductSearch(q);
  }, [searchParams]);

  const stateFilterOptions = useMemo(() => {
    const fromData = new Set(
      products.map((p) => String(p?.state || '').toUpperCase()).filter(Boolean),
    );
    const merged = new Set<string>([...PIPELINE_PRODUCT_STATES_FOR_FILTER, ...fromData]);
    return Array.from(merged).sort();
  }, [products]);

  const pipelineCategoryCounts = useMemo(
    () => countPipelineProductsByCategory(products as Record<string, unknown>[]),
    [products],
  );
  const pipelineCategoryCountsReady = totalProducts === 0 || products.length > 0;
  const pipelineCategoryCountsPartial = loadingMore && products.length > 0 && products.length < totalProducts;

  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      const bucket = bucketPipelineProductForCategoryFilter(p as Record<string, unknown>);
      const catOk = activeCategory === 'all' || bucket === activeCategory;
      if (!catOk) return false;

      const st = String(p?.state || '').toUpperCase();
      const stateOk = stateFilter === 'all' || st === stateFilter;
      if (!stateOk) return false;

      const listed = Boolean(p?.storefront_visible);
      const storefrontOk =
        storefrontFilter === 'all' ||
        (storefrontFilter === 'listed' ? listed : !listed);
      if (!storefrontOk) return false;

      const spec = p?.spec || {};
      const dp = String(p?.delivery_profile || spec?.delivery_profile || '').toLowerCase();
      const deliveryOk =
        deliveryProfileFilter === 'all' ||
        dp === deliveryProfileFilter ||
        (deliveryProfileFilter === 'landing_fast' && dp.includes('landing'));
      if (!deliveryOk) return false;

      const sf = p?.storefront_followup || {};
      const pipelinePaused = Boolean(sf.pipeline_on_hold);
      const inFocus = Boolean(p?.pipeline_focus_active);
      const workOk =
        pipelineWorkFilter === 'all' ||
        (pipelineWorkFilter === 'focus' && inFocus) ||
        (pipelineWorkFilter === 'paused' && pipelinePaused && !inFocus) ||
        (pipelineWorkFilter === 'active' && !pipelinePaused);
      if (!workOk) return false;

      if (repairRoundMin !== 'all') {
        const min = Number(repairRoundMin);
        const rr = Number(p?.quality_repair_round) || 0;
        if (rr < min) return false;
      }

      const start = localDateInputStartSeconds(createdFrom);
      const end = localDateInputEndSeconds(createdTo);
      if (start != null || end != null) {
        const raw = Number(p?.created_at) || 0;
        const createdSec = raw > 1e12 ? raw / 1000 : raw;
        if (!createdSec) return false;
        if (start != null && createdSec < start) return false;
        if (end != null && createdSec > end) return false;
      }

      const q = productSearch.trim().toLowerCase();
      if (!q) return true;
      const title = String(p?.spec?.product_name || p?.idea || '').toLowerCase();
      const id = String(p?.id || '').toLowerCase();
      const desc = String(p?.spec?.description || '').toLowerCase();
      const followup = String(p?.storefront_followup?.followup || '').toLowerCase();
      const profile = dp;
      return (
        title.includes(q) ||
        id.includes(q) ||
        desc.includes(q) ||
        followup.includes(q) ||
        profile.includes(q)
      );
    });
  }, [
    products,
    activeCategory,
    stateFilter,
    storefrontFilter,
    deliveryProfileFilter,
    pipelineWorkFilter,
    repairRoundMin,
    createdFrom,
    createdTo,
    productSearch,
  ]);

  const resetFilters = () => {
    setProductSearch('');
    setStateFilter('all');
    setStorefrontFilter('all');
    setDeliveryProfileFilter('all');
    setPipelineWorkFilter('all');
    setRepairRoundMin('all');
    setActiveCategory('all');
    setCreatedFrom('');
    setCreatedTo('');
  };

  return {
    activeCategory,
    setActiveCategory,
    productSearch,
    setProductSearch,
    stateFilter,
    setStateFilter,
    storefrontFilter,
    setStorefrontFilter,
    deliveryProfileFilter,
    setDeliveryProfileFilter,
    pipelineWorkFilter,
    setPipelineWorkFilter,
    repairRoundMin,
    setRepairRoundMin,
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
  };
}
