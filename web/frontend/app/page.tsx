import { cookies, headers } from 'next/headers';

import HomePage from './HomePage';
import FactoryLanding from '@/components/factory/FactoryLanding';
import { factoryLandingMetadata } from '@/components/factory/metadata';
import { isFactoryLanding } from '@/lib/siteRole';

export function generateMetadata() { return isFactoryLanding() ? factoryLandingMetadata('en') : {}; }
import { DocumentLang } from '@/components/DocumentLang';
import { SITE_LOCALE_COOKIE, resolveSiteLocale, asSiteLocale } from '@/lib/siteLocale';

// The locale is decided here, on the server, so the server render and the browser's
// hydration agree. HomePage used to detect it in the browser during its first render, and
// every non-English visitor got React #418 and a discarded server tree.
export default async function Page({ searchParams }: { searchParams: Promise<{ lang?: string | string[] }> }) {
  if (isFactoryLanding()) return <><DocumentLang locale="en" /><FactoryLanding initialLocale="en" /></>;
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  const lang = (await searchParams).lang;
  const requested = asSiteLocale(typeof lang === 'string' ? lang : null);
  const locale = requested ?? resolveSiteLocale(
    cookieStore.get(SITE_LOCALE_COOKIE)?.value,
    headerList.get('accept-language'),
  );
  return (
    <>
      <DocumentLang locale={locale} />
      <HomePage initialLocale={locale} explicitLocale={requested !== null} />
    </>
  );
}
