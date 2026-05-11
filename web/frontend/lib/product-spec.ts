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
