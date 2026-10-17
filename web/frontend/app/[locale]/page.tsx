import { notFound } from 'next/navigation';
import FactoryLanding from '@/components/factory/FactoryLanding';
import { factoryLandingMetadata } from '@/components/factory/metadata';
import { DocumentLang } from '@/components/DocumentLang';
import { isFactoryLanding } from '@/lib/siteRole';
import type { SiteLocale } from '@/lib/siteLocale';
type Props={params:Promise<{locale:string}>};
async function localeFor({params}:Props):Promise<SiteLocale> {
  const {locale}=await params;
  if(!isFactoryLanding() || !['ru','es','fr','zh'].includes(locale))notFound();
  return locale as SiteLocale;
}
export async function generateMetadata(props:Props){return factoryLandingMetadata(await localeFor(props));}
export default async function Page(props:Props){const locale=await localeFor(props);return <><DocumentLang locale={locale}/><FactoryLanding initialLocale={locale}/></>;}
