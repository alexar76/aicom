/**
 * Saved "product creation" presets (idea-adjacent fields only) — local browser storage.
 * Complements server-side reference_templates (YAML) with per-operator quick recipes.
 */

export type ProductCreationTemplate = {
  id: string;
  name: string;
  createdAt: number;
  deliveryChoice: 'full_software' | 'marketing_landing' | 'desktop_app' | 'infer';
  mode: 'prototype' | 'production';
  instructions: string;
};

const STORAGE_KEY = 'aicom_product_creation_templates_v1';
const MAX_TEMPLATES = 24;

function uid() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

export function listProductCreationTemplates(): ProductCreationTemplate[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return [];
    return arr
      .filter(
        (x): x is ProductCreationTemplate =>
          x &&
          typeof x === 'object' &&
          typeof (x as ProductCreationTemplate).id === 'string' &&
          typeof (x as ProductCreationTemplate).name === 'string',
      )
      .sort((a, b) => b.createdAt - a.createdAt);
  } catch {
    return [];
  }
}

export function upsertProductCreationTemplate(
  input: Omit<ProductCreationTemplate, 'id' | 'createdAt'> & { id?: string },
): ProductCreationTemplate {
  const row: ProductCreationTemplate = {
    id: input.id || uid(),
    name: input.name.trim() || 'Untitled',
    createdAt: Date.now(),
    deliveryChoice: input.deliveryChoice,
    mode: input.mode,
    instructions: input.instructions,
  };
  const prev = listProductCreationTemplates().filter((t) => t.id !== row.id);
  const next = [row, ...prev].slice(0, MAX_TEMPLATES);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* quota */
  }
  return row;
}

export function deleteProductCreationTemplate(id: string) {
  const next = listProductCreationTemplates().filter((t) => t.id !== id);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}
