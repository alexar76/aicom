import api from '@/lib/api';

export type StorefrontListableCount = {
  count: number | null;
  pending: boolean;
  stale: boolean;
  /** Card count from GET /api/products — matches what the vitrine renders. */
  verifiedCardCount: number | null;
};

/**
 * Public vitrine count aligned with rendered product cards (not a stale browser cache).
 * Uses a fast cached scan first, then verifies against GET /api/products when possible.
 */
export async function fetchPublicStorefrontListableCount(): Promise<number | null> {
  const detail = await fetchPublicStorefrontListableCountDetail();
  return detail.verifiedCardCount ?? detail.count;
}

export async function fetchPublicStorefrontListableCountDetail(): Promise<StorefrontListableCount> {
  let count: number | null = null;
  let pending = false;
  let stale = false;

  try {
    const meta = await api.getStorefrontCount();
    count = meta.count;
    pending = meta.pending;
    stale = meta.stale;
  } catch {
    try {
      const cats = await api.getCategories();
      count = cats.totalCount;
      pending = cats.pending;
      stale = cats.stale;
    } catch {
      return { count: null, pending: true, stale: false, verifiedCardCount: null };
    }
  }

  let verifiedCardCount: number | null = null;
  try {
    const products = await api.getProducts();
    verifiedCardCount = products.length;
    count = products.length;
    pending = false;
    stale = false;
  } catch {
    /* keep cached scan count */
  }

  return { count, pending, stale, verifiedCardCount };
}
