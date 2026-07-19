/** Normalize PM spec blocks — core_features / user_stories may be strings or objects. */

export function formatSpecFeature(feature: unknown): string {
  if (feature == null) return '';
  if (typeof feature === 'string') return feature;
  if (typeof feature === 'object') {
    const o = feature as Record<string, unknown>;
    const name = o.name != null ? String(o.name) : '';
    const desc = o.description != null ? String(o.description) : '';
    const pri = o.priority != null ? String(o.priority) : '';
    const parts = [name, desc].filter(Boolean).join(' — ');
    return pri ? `${parts}${parts ? ' · ' : ''}${pri}` : parts;
  }
  return String(feature);
}

export function formatUserStory(story: unknown): string {
  if (story == null) return '';
  if (typeof story === 'string') return story;
  if (typeof story === 'object') {
    const o = story as Record<string, unknown>;
    const s = o.story != null ? String(o.story) : '';
    const ac = o.acceptance_criteria != null ? String(o.acceptance_criteria) : '';
    if (s && ac) return `${s}\nAcceptance: ${ac}`;
    return s || ac;
  }
  return String(story);
}

const STACK_KEY_LABELS: Record<string, string> = {
  frontend: 'Frontend',
  backend: 'Backend',
  database: 'Database',
  data_store: 'Storage',
  infrastructure: 'Infrastructure',
  hosting: 'Hosting',
  messaging: 'Messaging',
  queue: 'Queue',
  cache: 'Cache',
  caching: 'Caching',
  search: 'Search',
  observability: 'Observability',
  plugins: 'Plugins & integrations',
  integrations: 'Integrations',
  ci_cd: 'CI/CD',
  api: 'API surface',
  runtime: 'Runtime',
  languages: 'Languages',
};

export function labelTechStackKey(key: string): string {
  return STACK_KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatFieldEntry(field: unknown): string {
  if (field == null) return '';
  if (typeof field === 'string') return field;
  if (typeof field === 'object') {
    const o = field as Record<string, unknown>;
    const name = o.name != null ? String(o.name) : '';
    const type = o.type != null ? String(o.type) : '';
    const desc = o.description != null ? String(o.description) : '';
    const fk = o.fk != null ? String(o.fk) : '';
    const bits = [name, type].filter(Boolean).join(': ');
    if (fk) return `${bits} → ${fk}`;
    if (desc) return `${bits} (${desc})`;
    return bits;
  }
  return String(field);
}

export function formatDataModelFields(fields: unknown): string {
  if (!Array.isArray(fields) || fields.length === 0) return '';
  return fields.map(formatFieldEntry).filter(Boolean).join(', ');
}

function formatRelationshipEntry(rel: unknown): string {
  if (rel == null) return '';
  if (typeof rel === 'string') return rel;
  if (typeof rel === 'object') {
    const o = rel as Record<string, unknown>;
    const name = o.name != null ? String(o.name) : '';
    const type = o.type != null ? String(o.type) : '';
    const to = o.to != null ? String(o.to) : '';
    if (name && type && to) return `${name} (${type}) → ${to}`;
    if (name && to) return `${name} → ${to}`;
    return [name, type, to].filter(Boolean).join(' · ');
  }
  return String(rel);
}

export function formatDataModelRelationships(relationships: unknown): string {
  if (relationships == null) return '';
  if (typeof relationships === 'string') return relationships;
  if (Array.isArray(relationships)) {
    return relationships.map(formatRelationshipEntry).filter(Boolean).join('; ');
  }
  return formatRelationshipEntry(relationships);
}
