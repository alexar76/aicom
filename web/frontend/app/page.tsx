import { cookies, headers } from 'next/headers';

import HomePage from './HomePage';
import { DocumentLang } from '@/components/DocumentLang';
import { SITE_LOCALE_COOKIE, resolveSiteLocale } from '@/lib/siteLocale';

// The locale is decided here, on the server, so the server render and the browser's
// hydration agree. HomePage used to detect it in the browser during its first render, and
// every non-English visitor got React #418 and a discarded server tree.
export default async function Page() {
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  const locale = resolveSiteLocale(
    cookieStore.get(SITE_LOCALE_COOKIE)?.value,
    headerList.get('accept-language'),
  );
  return (
    <>
      <DocumentLang locale={locale} />
      <HomePage initialLocale={locale} />
    </>
  );
}
