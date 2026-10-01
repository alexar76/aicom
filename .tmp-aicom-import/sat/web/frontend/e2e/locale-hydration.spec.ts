import { expect, test, type Browser } from '@playwright/test';

// The home page and /docs detected the visitor's language in the browser during their first
// render. The server rendered English, a Russian browser rendered Russian, and React threw
// the server tree away (#418) for every visitor who was not English. The server now resolves
// the locale (cookie, else Accept-Language) and the page hydrates with the same value.

const HYDRATION = /hydrat|didn't match|Minified React error #4(18|23|25)/i;

type Case = {
  name: string;
  path: '/' | '/docs';
  browserLocale: string;
  stored?: string;
  cookie?: string;
  want: string;
};

const CASES: Case[] = [
  { name: 'a Russian browser', path: '/', browserLocale: 'ru-RU', want: 'ru' },
  { name: 'an English browser', path: '/', browserLocale: 'en-US', want: 'en' },
  { name: 'a choice saved only in localStorage', path: '/', browserLocale: 'ru-RU', stored: 'fr', want: 'fr' },
  { name: 'a choice saved in the cookie', path: '/', browserLocale: 'ru-RU', cookie: 'es', want: 'es' },
  { name: 'docs in a Russian browser', path: '/docs', browserLocale: 'ru-RU', want: 'ru' },
  { name: 'docs with a choice in localStorage', path: '/docs', browserLocale: 'en-US', stored: 'zh', want: 'zh' },
];

async function open(browser: Browser, baseURL: string, c: Case) {
  const context = await browser.newContext({ locale: c.browserLocale });
  if (c.cookie) await context.addCookies([{ name: 'marketing_locale', value: c.cookie, url: baseURL }]);
  if (c.stored) {
    await context.addInitScript((value) => {
      if (!sessionStorage.getItem('seeded')) {
        localStorage.setItem('marketing_locale', value);
        sessionStorage.setItem('seeded', '1');
      }
    }, c.stored);
  }
  const page = await context.newPage();
  const hydration: string[] = [];
  page.on('console', (m) => HYDRATION.test(m.text()) && hydration.push(m.text().slice(0, 200)));
  page.on('pageerror', (e) => HYDRATION.test(e.message) && hydration.push(e.message.slice(0, 200)));
  return { context, page, hydration };
}

for (const c of CASES) {
  test(`${c.name} hydrates in ${c.want} without a mismatch`, async ({ browser, baseURL }) => {
    const { context, page, hydration } = await open(browser, baseURL!, c);
    await page.goto(c.path);
    await expect.poll(() => page.evaluate(() => document.documentElement.lang)).toBe(c.want);
    await page.waitForTimeout(1_000);
    expect(hydration).toEqual([]);
    if (c.stored || c.cookie) {
      // Saved where the server looks, so the next request renders in the chosen language.
      const cookies = await context.cookies();
      expect(cookies.find((k) => k.name === 'marketing_locale')?.value).toBe(c.want);
    }
    await context.close();
  });
}

test('the server declares the document language before any script of ours runs', async ({ request }) => {
  // The root layout is static and says lang="en"; the page sets it while the HTML is parsed.
  for (const [header, want] of [['ru-RU,ru;q=0.9', 'ru'], ['de-DE,fr;q=0.8', 'fr'], ['en-US', 'en']]) {
    for (const path of ['/', '/docs']) {
      const html = await (await request.get(path, { headers: { 'accept-language': header } })).text();
      expect(html, `${path} for ${header}`).toContain(`document.documentElement.lang="${want}"`);
    }
  }
});
