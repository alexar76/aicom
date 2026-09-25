import { cookies, headers } from 'next/headers';

import DocsPage from './DocsPage';
import { DocumentLang } from '@/components/DocumentLang';
import { SITE_LOCALE_COOKIE, resolveSiteLocale } from '@/lib/siteLocale';

// Decided on the server for the same reason as the home page: see app/page.tsx.
export default async function Page() {
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  const locale = resolveSiteLocale(
    cookieStore.get(SITE_LOCALE_COOKIE)?.value,
    headerList.get('accept-language'),
  );
  return (
    <>
      <DocumentLang locale={locale} />
      <DocsPage initialLocale={locale} />
    </>
  );
}
