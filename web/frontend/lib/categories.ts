/** Shared category labels for storefront / SEO explore pages */
import type { Product } from './api';

/** Match the public API's shelf split: landings separately, apps by vertical. */
export function productsForExploreCategory(products: Product[], category: string): Product[] {
  return products.filter(product => category === 'landings'
    ? product.delivery_profile === 'marketing_landing'
    : product.delivery_profile !== 'marketing_landing' && (product.category || 'uncategorized') === category);
}

export const CATEGORY_LABELS: Record<string, string> = {
  /** Marketing landings only — not mixed into SaaS / IoT / other verticals */
  landings: 'Landing pages',
  ai_ml: 'AI/ML',
  devtools: 'DevTools',
  fintech: 'FinTech',
  saas: 'SaaS',
  ecommerce: 'E-Commerce',
  iot: 'IoT',
  security: 'Security',
  productivity: 'Productivity',
  career: 'Career',
  desktop: 'Desktop apps',
};

export const CATEGORY_EMOJIS: Record<string, string> = {
  landings: '🎯',
  ai_ml: '🧠',
  devtools: '🛠️',
  fintech: '💰',
  saas: '☁️',
  ecommerce: '🛒',
  iot: '📡',
  security: '🔒',
  productivity: '⚡',
  career: '💼',
  desktop: '🖥️',
  uncategorized: '📁',
};

export const EXPLORE_SLUGS = Object.keys(CATEGORY_LABELS) as string[];
