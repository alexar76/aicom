/**
 * localStorage snapshot for the public storefront catalog (home #products).
 * Cache-first paint, then background revalidate against /api/products.
 */

import type { Product } from '@/lib/api';

export const STOREFRONT_CATALOG_CACHE_VERSION = 1 as const;

export type StorefrontCatalogCategory = {
  id: string;
  name: string;
  icon: string;
  description: string;
  product_count: number;
};

export type StorefrontCatalogSnapshot = {
  products: Product[];
  categories: StorefrontCatalogCategory[];
  totalCount: number;
  savedAt: number;
};

type StoredEnvelope = {
  v: typeof STOREFRONT_CATALOG_CACHE_VERSION;
  ts: number;
  category: string;
  products: Product[];
  categories: StorefrontCatalogCategory[];
  totalCount: number;
};

export function normalizeStorefrontCategoryKey(category?: string | null): string {
  const raw = (category ?? 'all').trim();
  return raw && raw !== 'all' ? raw : 'all';
}

export function storefrontCatalogCacheKey(category?: string | null): string {
  return `aicom_storefront_catalog_v${STOREFRONT_CATALOG_CACHE_VERSION}_${normalizeStorefrontCategoryKey(category)}`;
}

function isCategoryRow(x: unknown): x is StorefrontCatalogCategory {
  if (!x || typeof x !== 'object') return false;
  const o = x as StorefrontCatalogCategory;
  return typeof o.id === 'string' && typeof o.name === 'string';
}

function isProductRow(x: unknown): x is Product {
  return Boolean(x && typeof x === 'object' && typeof (x as Product).id === 'string');
}

export function readStorefrontCatalogCache(
  category?: string | null,
): StorefrontCatalogSnapshot | null {
  if (typeof window === 'undefined') return null;
  const key = normalizeStorefrontCategoryKey(category);
  try {
    const raw = localStorage.getItem(storefrontCatalogCacheKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredEnvelope>;
    if (!parsed || parsed.v !== STOREFRONT_CATALOG_CACHE_VERSION) return null;
    if (parsed.category !== key) return null;
    if (!Array.isArray(parsed.products) || !Array.isArray(parsed.categories)) return null;
    const products = parsed.products.filter(isProductRow);
    const categories = parsed.categories.filter(isCategoryRow);
    const totalCount =
      typeof parsed.totalCount === 'number' && Number.isFinite(parsed.totalCount)
        ? parsed.totalCount
        : products.length;
    const savedAt = typeof parsed.ts === 'number' ? parsed.ts : 0;
    if (products.length === 0 && categories.length === 0) return null;
    return { products, categories, totalCount, savedAt };
  } catch {
    return null;
  }
}

export function writeStorefrontCatalogCache(
  category: string | null | undefined,
  snapshot: StorefrontCatalogSnapshot,
): void {
  if (typeof window === 'undefined') return;
  const key = normalizeStorefrontCategoryKey(category);
  try {
    const payload: StoredEnvelope = {
      v: STOREFRONT_CATALOG_CACHE_VERSION,
      ts: snapshot.savedAt || Date.now(),
      category: key,
      products: snapshot.products,
      categories: snapshot.categories,
      totalCount: snapshot.totalCount,
    };
    localStorage.setItem(storefrontCatalogCacheKey(key), JSON.stringify(payload));
  } catch {
    /* quota */
  }
}

export function clearStorefrontCatalogCache(): void {
  if (typeof window === 'undefined') return;
  try {
    const prefix = `aicom_storefront_catalog_v${STOREFRONT_CATALOG_CACHE_VERSION}_`;
    const toRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith(prefix)) toRemove.push(k);
    }
    for (const k of toRemove) localStorage.removeItem(k);
  } catch {
    /* ignore */
  }
}
