import { rememberSiteLocale } from '@/lib/siteLocale';
import en from '../../language-packs/docs/en.json';
import ru from '../../language-packs/docs/ru.json';
import es from '../../language-packs/docs/es.json';
import fr from '../../language-packs/docs/fr.json';
import zh from '../../language-packs/docs/zh.json';
import type { DocLocale, DocsStrings } from './types';

export type { DocLocale, DocsStrings } from './types';

const PACKS: Record<DocLocale, DocsStrings> = { en, ru, es, fr, zh };

export function getDocsStrings(locale?: string | null): DocsStrings {
  const raw = (locale || '').toLowerCase();
  if (raw.startsWith('ru')) return PACKS.ru;
  if (raw.startsWith('es')) return PACKS.es;
  if (raw.startsWith('fr')) return PACKS.fr;
  if (raw.startsWith('zh')) return PACKS.zh;
  return PACKS.en;
}

/** A choice saved in this browser (shared marketing_locale first, then docs-locale), or null. */
export function detectStoredDocLocale(): DocLocale | null {
  if (typeof window === 'undefined') return null;
  try {
    for (const key of ['marketing_locale', 'docs-locale']) {
      const v = localStorage.getItem(key);
      if (v === 'ru' || v === 'es' || v === 'en' || v === 'fr' || v === 'zh') return v;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function saveDocLocale(locale: DocLocale): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem('docs-locale', locale);
    localStorage.setItem('marketing_locale', locale);
  } catch {
    /* ignore */
  }
  rememberSiteLocale(locale);
  document.documentElement.lang = locale;
  window.dispatchEvent(new CustomEvent('marketing-locale-changed', { detail: locale }));
}
