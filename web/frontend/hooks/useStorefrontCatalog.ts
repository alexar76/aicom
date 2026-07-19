'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import api, { type Product } from '@/lib/api';
import {
  readStorefrontCatalogCache,
  writeStorefrontCatalogCache,
  type StorefrontCatalogCategory,
  type StorefrontCatalogSnapshot,
} from '@/lib/storefrontCatalogCache';

export type UseStorefrontCatalogResult = {
  products: Product[];
  categories: StorefrontCatalogCategory[];
  catalogTotalCount: number;
  loading: boolean;
  refreshing: boolean;
  fromCache: boolean;
  error: string | null;
  revalidate: () => void;
};

function applySnapshot(
  snap: StorefrontCatalogSnapshot,
  setters: {
    setProducts: (p: Product[]) => void;
    setCategories: (c: StorefrontCatalogCategory[]) => void;
    setCatalogTotalCount: (n: number) => void;
  },
): void {
  setters.setProducts(snap.products);
  setters.setCategories(snap.categories);
  setters.setCatalogTotalCount(snap.totalCount);
}

export function useStorefrontCatalog(activeCategory: string): UseStorefrontCatalogResult {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<StorefrontCatalogCategory[]>([]);
  const [catalogTotalCount, setCatalogTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(async (catId: string) => {
    const seq = ++requestSeq.current;
    const cat = catId?.trim() || 'all';
    const cached = readStorefrontCatalogCache(cat);
    const hadCache = Boolean(cached);

    if (hadCache && cached) {
      applySnapshot(cached, { setProducts, setCategories, setCatalogTotalCount });
      setFromCache(true);
      setLoading(false);
      setRefreshing(true);
      setError(null);
    } else {
      setLoading(true);
      setRefreshing(false);
      setFromCache(false);
      setError(null);
    }

    const friendlyLoadError = 'Catalog is temporarily unavailable. Please retry in a moment.';

    const fetchOnce = async () => {
      const prods = await (cat !== 'all' ? api.getProducts(cat) : api.getProducts());
      let categories = readStorefrontCatalogCache('all')?.categories ?? [];
      const totalCount = prods.length;
      try {
        const catPayload = await api.getCategories();
        categories = catPayload.categories;
      } catch {
        /* products loaded — category tabs can catch up on next refresh */
      }
      return { prods, categories, totalCount };
    };

    try {
      let payload = await fetchOnce();
      if (payload.prods.length === 0) {
        await new Promise((r) => setTimeout(r, 1500));
        if (seq !== requestSeq.current) return;
        payload = await fetchOnce();
      }
      if (seq !== requestSeq.current) return;

      const snapshot: StorefrontCatalogSnapshot = {
        products: payload.prods,
        categories: payload.categories,
        totalCount: payload.totalCount,
        savedAt: Date.now(),
      };
      applySnapshot(snapshot, { setProducts, setCategories, setCatalogTotalCount });
      writeStorefrontCatalogCache(cat, snapshot);
      setFromCache(false);
      setError(null);
    } catch (err: unknown) {
      if (seq !== requestSeq.current) return;
      if (hadCache) {
        setError(null);
      } else {
        setError(friendlyLoadError);
        setProducts([]);
        setCategories([]);
        setCatalogTotalCount(0);
      }
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load(activeCategory);
  }, [activeCategory, load]);

  const revalidate = useCallback(() => {
    void load(activeCategory);
  }, [activeCategory, load]);

  return {
    products,
    categories,
    catalogTotalCount,
    loading,
    refreshing,
    fromCache,
    error,
    revalidate,
  };
}
