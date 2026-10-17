import type { Metadata } from 'next';
import { factoryCopy } from './copy';
import type { SiteLocale } from '@/lib/siteLocale';
export function factoryLandingMetadata(locale: SiteLocale): Metadata {
  const copy=factoryCopy[locale];
  const title=`AICOM — ${copy.title.join(' ')}`;
  const path=locale==='en'?'/':`/${locale}/`;
  return {metadataBase:new URL('https://modeldev.modelmarket.dev'),title:{absolute:title},description:copy.intro,
    alternates:{canonical:path,languages:{en:'/',ru:'/ru/',es:'/es/',fr:'/fr/',zh:'/zh/','x-default':'/'}},
    openGraph:{title,description:copy.intro,url:path,type:'website',images:['/factory/social.png']},
    twitter:{card:'summary_large_image',title,description:copy.intro,images:['/factory/social.png']}};
}
