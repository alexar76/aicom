/**
 * The visitor's language, decided so the server render and the browser agree.
 *
 * Pages that detected it during their first render in the browser (navigator.language,
 * localStorage) rendered English on the server and Russian in a Russian browser, and React
 * threw the server tree away (#418) for every visitor who was not English. The server now
 * resolves it from the saved choice (this cookie) or Accept-Language and hands it to the
 * page as its initial state; the browser only adopts a choice the server could not see.
 */
export type SiteLocale = 'en' | 'ru' | 'es' | 'fr' | 'zh';

/** Same name as the localStorage key the switchers have always written. */
export const SITE_LOCALE_COOKIE = 'marketing_locale';

const ONE_YEAR_S = 60 * 60 * 24 * 365;

export function asSiteLocale(raw: string | null | undefined): SiteLocale | null {
  const v = (raw || '').trim().toLowerCase();
  if (v.startsWith('ru')) return 'ru';
  if (v.startsWith('es')) return 'es';
  if (v.startsWith('fr')) return 'fr';
  if (v.startsWith('zh')) return 'zh';
  if (v.startsWith('en')) return 'en';
  return null;
}

/** What both passes render before anything about the visitor is known. */
export function defaultSiteLocale(): SiteLocale {
  return asSiteLocale(process.env.NEXT_PUBLIC_MARKETING_LOCALE) ?? 'en';
}

/** Server side: the saved choice, else the best Accept-Language match, else the default. */
export function resolveSiteLocale(
  cookie: string | null | undefined,
  acceptLanguage: string | null | undefined,
): SiteLocale {
  const saved = asSiteLocale(cookie);
  if (saved) return saved;
  const ranked = (acceptLanguage || '')
    .split(',')
    .map((part, index) => {
      const [tag, ...params] = part.trim().split(';');
      const q = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
      return { tag: tag.trim(), q: q === undefined ? 1 : Number(q.slice(2)), index };
    })
    .filter((entry) => entry.tag && Number.isFinite(entry.q) && entry.q > 0)
    .sort((a, b) => b.q - a.q || a.index - b.index);
  for (const { tag } of ranked) {
    const locale = asSiteLocale(tag);
    if (locale) return locale;
  }
  return defaultSiteLocale();
}

/** A choice saved only in localStorage, which the server cannot read. */
export function storedSiteLocale(): SiteLocale | null {
  if (typeof window === 'undefined') return null;
  try {
    return asSiteLocale(window.localStorage.getItem(SITE_LOCALE_COOKIE));
  } catch {
    return null;
  }
}

/** The choice saved in the cookie, read in the browser. */
export function cookieSiteLocale(): SiteLocale | null {
  if (typeof document === 'undefined') return null;
  const hit = document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith(`${SITE_LOCALE_COOKIE}=`));
  return hit ? asSiteLocale(hit.slice(SITE_LOCALE_COOKIE.length + 1)) : null;
}

/**
 * In the browser: the saved choice, else the SAME ranking the server applies to
 * Accept-Language, over navigator.languages (the list the browser sends as that header).
 * Looking only at navigator.language, and never matching 'en', left the widget and the nav
 * in English on a page the server had rendered in Russian for a [uk, ru] browser.
 */
export function browserSiteLocale(): SiteLocale {
  const saved = storedSiteLocale() ?? cookieSiteLocale();
  if (saved) return saved;
  if (typeof navigator === 'undefined') return defaultSiteLocale();
  const languages = navigator.languages?.length ? navigator.languages.join(',') : navigator.language;
  return resolveSiteLocale(null, languages);
}

/** Save the choice where the server looks for it on the next request. */
export function rememberSiteLocale(locale: SiteLocale): void {
  if (typeof document === 'undefined') return;
  const secure = window.location.protocol === 'https:' ? '; secure' : '';
  document.cookie = `${SITE_LOCALE_COOKIE}=${locale}; path=/; max-age=${ONE_YEAR_S}; samesite=lax${secure}`;
}
