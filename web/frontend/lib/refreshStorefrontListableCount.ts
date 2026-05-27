import api from '@/lib/api';

/** Same source as public vitrine tabs (`GET /api/products/categories`). */
export async function fetchPublicStorefrontListableCount(): Promise<number | null> {
  try {
    const { totalCount } = await api.getCategories();
    return typeof totalCount === 'number' && Number.isFinite(totalCount) ? totalCount : null;
  } catch {
    return null;
  }
}
