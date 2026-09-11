'use client';

import Script from 'next/script';
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

const site = (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:9080').replace(/\/$/, '');

/** Embeddable AI Market panel — storefront only (not admin). */
export function AiMarketWidgetLoader() {
  const pathname = usePathname() || '';
  const onAdmin = pathname.startsWith('/admin');

  // Belt-and-suspenders: ensure script runs if next/script is delayed
  useEffect(() => {
    if (onAdmin) return;
    if (document.querySelector('script[src*="aimarket.js"]')) return;
    const s = document.createElement('script');
    s.src = '/aimarket.js';
    s.async = true;
    s.setAttribute('data-theme', 'auto');
    s.setAttribute('data-intent', '');
    s.setAttribute('data-budget', '3.00');
    s.setAttribute('data-hub-url', site);
    s.setAttribute('data-affiliate-id', 'aifactory_storefront');
    document.body.appendChild(s);
  }, [onAdmin]);

  if (onAdmin) return null;

  return (
    <Script
      id="aimarket-widget-script"
      src="/aimarket.js"
      strategy="afterInteractive"
      data-theme="auto"
      data-intent=""
      data-budget="3.00"
      data-hub-url={site}
      data-affiliate-id="aifactory_storefront"
    />
  );
}
