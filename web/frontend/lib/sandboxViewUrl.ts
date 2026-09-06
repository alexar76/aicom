import { detectAdminLocale, type AdminLocale } from '@/lib/adminI18n';

/** Append admin UI locale to sandbox viewer / file URLs so server-side badges match. */
export function withSandboxLocale(url: string, locale?: AdminLocale | string | null): string {
  const loc =
    locale === 'ru' || locale === 'es' || locale === 'en'
      ? locale
      : detectAdminLocale();
  try {
    const base =
      typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const parsed = url.startsWith('http') ? new URL(url) : new URL(url, base);
    parsed.searchParams.set('lang', loc);
    return url.startsWith('http') ? parsed.href : `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}lang=${encodeURIComponent(loc)}`;
  }
}
