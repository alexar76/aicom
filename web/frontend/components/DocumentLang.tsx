import type { SiteLocale } from '@/lib/siteLocale';

/**
 * Sets <html lang> while the server's HTML is still being parsed.
 *
 * The root layout stays static, so it says lang="en"; reading the locale there would make
 * every route dynamic. A page whose body the server rendered in the visitor's language
 * renders this, so the document language matches before hydration too. `locale` is one of
 * the five SiteLocale values, never request text.
 */
export function DocumentLang({ locale }: { locale: SiteLocale }) {
  return <script dangerouslySetInnerHTML={{ __html: `document.documentElement.lang=${JSON.stringify(locale)}` }} />;
}
