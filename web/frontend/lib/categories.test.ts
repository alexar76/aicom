import { describe, expect, it } from 'vitest';
import type { Product } from './api';
import { productsForExploreCategory } from './categories';

const products = [
  { id: 'landing', delivery_profile: 'marketing_landing', category: 'saas', state: 'QA_REVIEW' },
  { id: 'app', delivery_profile: 'full_software', category: 'saas', state: 'COMPLETED' },
  { id: 'desktop', delivery_profile: 'desktop_app', category: 'desktop' },
  { id: 'legacy', category: 'saas' },
  { id: 'uncategorized' },
] as Product[];

describe('public catalog shelves', () => {
  it('keeps published landings visible during repair and out of app verticals', () => {
    expect(productsForExploreCategory(products, 'landings').map(p => p.id)).toEqual(['landing']);
    expect(productsForExploreCategory(products, 'saas').map(p => p.id)).toEqual(['app', 'legacy']);
  });
  it('retains desktop and uncategorized products', () => {
    expect(productsForExploreCategory(products, 'desktop').map(p => p.id)).toEqual(['desktop']);
    expect(productsForExploreCategory(products, 'uncategorized').map(p => p.id)).toEqual(['uncategorized']);
  });
});
