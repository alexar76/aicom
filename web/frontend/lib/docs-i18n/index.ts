import en from '../../language-packs/docs/en.json';
import ru from '../../language-packs/docs/ru.json';
import es from '../../language-packs/docs/es.json';
import type { DocLocale, DocsStrings } from './types';

export type { DocLocale, DocsStrings } from './types';

const PACKS: Record<DocLocale, DocsStrings> = { en, ru, es };

export function getDocsStrings(locale?: string | null): DocsStrings {
  const raw = (locale || '').toLowerCase();
  if (raw.startsWith('ru')) return PACKS.ru;
  if (raw.startsWith('es')) return PACKS.es;
  return PACKS.en;
}

export function detectDocLocale(): DocLocale {
  if (typeof window === 'undefined') {
    const env = (process.env.NEXT_PUBLIC_MARKETING_LOCALE || '').toLowerCase();
    if (env.startsWith('ru')) return 'ru';
    if (env.startsWith('es')) return 'es';
    return 'en';
  }
  try {
    const shared = localStorage.getItem('marketing_locale');
    if (shared === 'ru' || shared === 'es' || shared === 'en') return shared;
    const docs = localStorage.getItem('docs-locale');
    if (docs === 'ru' || docs === 'es' || docs === 'en') return docs;
  } catch {
    /* ignore */
  }
  const nav = navigator.language.toLowerCase();
  if (nav.startsWith('ru')) return 'ru';
  if (nav.startsWith('es')) return 'es';
  return 'en';
}

export function saveDocLocale(locale: DocLocale): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem('docs-locale', locale);
    localStorage.setItem('marketing_locale', locale);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = locale;
  window.dispatchEvent(new CustomEvent('marketing-locale-changed', { detail: locale }));
}
