/**
 * Bucket pipeline rows for the admin Pipeline Monitor category filter.
 * Keeps dropdown counts aligned with total pipeline size (not storefront-only /api/products/categories).
 */

const MARKETPLACE_SLUGS = new Set([
  'ai_ml',
  'devtools',
  'fintech',
  'saas',
  'ecommerce',
  'iot',
  'security',
  'productivity',
]);

/** Same order as storefront CATEGORIES (landings first), then Other. */
export const PIPELINE_CATEGORY_FILTER_ORDER: readonly string[] = [
  'landings',
  'ai_ml',
  'devtools',
  'fintech',
  'saas',
  'ecommerce',
  'iot',
  'security',
  'productivity',
  'uncategorized',
];

export function slugToMarketplaceCategory(raw: unknown): string | null {
  if (raw == null) return null;
  const s0 = String(raw).trim();
  if (!s0) return null;
  const s = s0.toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
  const aliases: Record<string, string | null> = {
    'ai/ml': 'ai_ml',
    machine_learning: 'ai_ml',
    artificial_intelligence: 'ai_ml',
    generative_ai: 'ai_ml',
    ml: 'ai_ml',
    llm: 'ai_ml',
    dev_tools: 'devtools',
    developer_tools: 'devtools',
    fintech: 'fintech',
    fin_tech: 'fintech',
    finance: 'fintech',
    payments: 'fintech',
    e_commerce: 'ecommerce',
    ecommerce: 'ecommerce',
    'e-commerce': 'ecommerce',
    retail: 'ecommerce',
    saas: 'saas',
    software_as_a_service: 'saas',
    b2b_saas: 'saas',
    iot: 'iot',
    internet_of_things: 'iot',
    embedded: 'iot',
    security: 'security',
    cybersecurity: 'security',
    infosec: 'security',
    productivity: 'productivity',
    collaboration: 'productivity',
    workflow: 'productivity',
    uncategorized: null,
    other: null,
    general: null,
    misc: null,
    technology: null,
    business: null,
    software: null,
  };
  const mapped = s in aliases ? aliases[s]! : s;
  if (mapped === null) return null;
  if (MARKETPLACE_SLUGS.has(mapped)) return mapped;
  return null;
}

function normalizeDeliveryProfile(raw: string): string {
  const key = raw.trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
  if (!key) return 'full_software';
  if (['marketing_landing', 'marketing', 'landing_only', 'promo_only', 'brochure'].includes(key)) {
    return 'marketing_landing';
  }
  return 'full_software';
}

function resolvedDeliveryProfile(product: Record<string, unknown>, specInner: Record<string, unknown> | null): string | null {
  let raw: unknown = null;
  if (specInner && typeof specInner.delivery_profile === 'string' && specInner.delivery_profile) {
    raw = specInner.delivery_profile;
  } else if (typeof product.delivery_profile === 'string' && product.delivery_profile) {
    raw = product.delivery_profile;
  }
  if (raw == null) return null;
  return normalizeDeliveryProfile(String(raw));
}

function getSpecInner(spec: unknown): Record<string, unknown> | null {
  if (!spec || typeof spec !== 'object') return null;
  const s = spec as Record<string, unknown>;
  const inner = s.specification;
  if (inner && typeof inner === 'object') return inner as Record<string, unknown>;
  return s;
}

function inferCategoryFromSignals(product: Record<string, unknown>): string | null {
  const parts: string[] = [String(product.idea || '')];
  const tags = product.tags;
  if (Array.isArray(tags)) {
    for (const t of tags) parts.push(String(t));
  }
  const spec = product.spec;
  if (spec && typeof spec === 'object') {
    const sp = spec as Record<string, unknown>;
    const inner = (sp.specification as Record<string, unknown>) || sp;
    for (const k of ['description', 'product_name'] as const) {
      if (typeof inner[k] === 'string') parts.push(inner[k] as string);
    }
  }
  const sm = product.storefront_marketing_copy;
  if (sm && typeof sm === 'object') {
    const m = sm as Record<string, unknown>;
    for (const k of ['long_description', 'short_description', 'tagline'] as const) {
      if (typeof m[k] === 'string') parts.push(m[k] as string);
    }
    const seo = m.seo_metadata;
    if (seo && typeof seo === 'object') {
      const kw = (seo as Record<string, unknown>).keywords;
      if (Array.isArray(kw)) parts.push(kw.map((x) => String(x)).join(' '));
    }
  }
  const blob = parts.join(' ').toLowerCase();
  const rules: [string, string[]][] = [
    ['ai_ml', ['llm', 'gpt', 'neural', 'embedding', 'classifier', 'inference', 'training data', 'torch', 'tensorflow']],
    ['devtools', ['cli for dev', 'git hook', 'cicd', 'linter', 'compiler', 'sdk', 'debugger', 'api client', 'localhost']],
    ['fintech', ['payment', 'invoice', 'ledger', 'portfolio', 'defi', 'trading', 'budget', 'expense', 'receipt', 'tax']],
    ['ecommerce', ['cart', 'checkout', 'catalog', 'sku', 'inventory', 'dropship', 'seller', 'storefront']],
    ['iot', ['sensor', 'mqtt', 'firmware', 'embedded', 'smart device', 'edge device']],
    ['security', ['sso', 'oauth', 'encrypt', 'vulnerability', 'xss', 'audit log', 'secrets', 'mfa']],
    ['productivity', ['kanban', 'calendar', 'reminder', 'notes app', 'tasks', 'time track', 'meeting']],
    ['saas', ['dashboard', 'crm', 'subscription', 'workspace', 'team', 'multi-tenant']],
  ];
  for (const [catId, kws] of rules) {
    if (kws.some((k) => blob.includes(k))) return catId;
  }
  return null;
}

/** Single category bucket id for filtering and counting (matches card badges when applied). */
export function bucketPipelineProductForCategoryFilter(product: Record<string, unknown>): string {
  const specInner = getSpecInner(product.spec);
  if (resolvedDeliveryProfile(product, specInner) === 'marketing_landing') {
    return 'landings';
  }
  const p = slugToMarketplaceCategory(product.category);
  if (p) return p;
  const inferred = inferCategoryFromSignals(product);
  if (inferred) return inferred;
  return 'uncategorized';
}

export function countPipelineProductsByCategory(products: Record<string, unknown>[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const id of PIPELINE_CATEGORY_FILTER_ORDER) {
    out[id] = 0;
  }
  for (const raw of products) {
    const b = bucketPipelineProductForCategoryFilter(raw);
    out[b] = (out[b] || 0) + 1;
  }
  return out;
}
