import { afterEach, describe, expect, it, vi } from 'vitest';

import { asSiteLocale, browserSiteLocale, defaultSiteLocale, resolveSiteLocale } from './siteLocale';

describe('resolveSiteLocale', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('prefers the saved choice over the browser language', () => {
    expect(resolveSiteLocale('es', 'ru-RU,ru;q=0.9,en;q=0.8')).toBe('es');
  });

  it('uses the best-ranked supported Accept-Language entry', () => {
    expect(resolveSiteLocale(undefined, 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('ru');
    expect(resolveSiteLocale(undefined, 'de-DE,de;q=0.9,fr;q=0.8,en;q=0.7')).toBe('fr');
    expect(resolveSiteLocale(undefined, 'zh-CN')).toBe('zh');
  });

  it('ranks by q, not by position', () => {
    expect(resolveSiteLocale(null, 'en;q=0.4,ru;q=0.9')).toBe('ru');
  });

  it('ignores refused and malformed entries', () => {
    expect(resolveSiteLocale(null, 'ru;q=0,fr;q=abc,es;q=0.5')).toBe('es');
    expect(resolveSiteLocale(null, '*')).toBe('en');
  });

  it('ignores a cookie that is not a supported locale', () => {
    expect(resolveSiteLocale('../../etc', 'fr')).toBe('fr');
  });

  it('falls back to the configured default', () => {
    vi.stubEnv('NEXT_PUBLIC_MARKETING_LOCALE', 'ru');
    expect(resolveSiteLocale(undefined, 'de')).toBe('ru');
    expect(defaultSiteLocale()).toBe('ru');
  });

  it('maps regional tags to their language', () => {
    expect(asSiteLocale('es-419')).toBe('es');
    expect(asSiteLocale('EN-gb')).toBe('en');
    expect(asSiteLocale('pt-BR')).toBeNull();
  });
});

describe('browserSiteLocale agrees with the server', () => {
  function stubBrowser({ languages, stored, cookie }: { languages: string[]; stored?: string; cookie?: string }) {
    const store = new Map<string, string>(stored ? [['marketing_locale', stored]] : []);
    vi.stubGlobal('window', {
      localStorage: { getItem: (k: string) => store.get(k) ?? null },
      location: { protocol: 'https:' },
    });
    vi.stubGlobal('document', { cookie: cookie ?? '' });
    vi.stubGlobal('navigator', { languages, language: languages[0] });
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('ranks the whole language list the way resolveSiteLocale ranks Accept-Language', () => {
    // A [uk, ru] browser: the server renders ru, so the widget must too, not the default.
    stubBrowser({ languages: ['uk-UA', 'uk', 'ru', 'en'] });
    expect(browserSiteLocale()).toBe(resolveSiteLocale(null, 'uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7'));
    expect(browserSiteLocale()).toBe('ru');
  });

  it('treats an English browser as a preference over the configured default', () => {
    vi.stubEnv('NEXT_PUBLIC_MARKETING_LOCALE', 'ru');
    stubBrowser({ languages: ['en-US', 'en'] });
    expect(browserSiteLocale()).toBe('en');
    expect(resolveSiteLocale(null, 'en-US,en;q=0.9')).toBe('en');
  });

  it('prefers localStorage, then the cookie, then the language list', () => {
    stubBrowser({ languages: ['ru'], stored: 'fr', cookie: 'marketing_locale=es' });
    expect(browserSiteLocale()).toBe('fr');
    stubBrowser({ languages: ['ru'], cookie: 'theme=dark; marketing_locale=es' });
    expect(browserSiteLocale()).toBe('es');
  });
});
