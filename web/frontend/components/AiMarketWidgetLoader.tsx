'use client';

import Script from 'next/script';
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';

const site = (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:9080').replace(/\/$/, '');

/** Load the optional market only after a visitor opens it; keep the workspace unobstructed. */
export function AiMarketWidgetLoader() {
  const pathname = usePathname() || '';
  const onAdmin = pathname.startsWith('/admin');
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const host = document.getElementById('aimarket-widget-host');
    if (host) host.style.display = open && !onAdmin ? '' : 'none';
  }, [open, onAdmin]);
  if (onAdmin) return null;
  return <>
    <button type="button" aria-expanded={open} aria-label="AIMarket" className="fixed bottom-4 left-4 z-40 rounded-full border border-cyan-400/30 bg-slate-950 px-4 py-3 text-sm text-cyan-200 shadow-lg" onClick={() => { setLoaded(true); setOpen(!open); }}>
      {open ? '× AIMarket' : 'AIMarket ↗'}
    </button>
    {loaded && <Script id="aimarket-widget-script" src="/aimarket.js" strategy="afterInteractive" data-theme="auto" data-intent="" data-budget="3.00" data-hub-url={site} data-affiliate-id="aifactory_storefront" onReady={() => {
      const host = document.getElementById('aimarket-widget-host');
      if (host) { host.style.display = open ? '' : 'none'; host.style.bottom = '76px'; }
    }} onError={() => { setLoaded(false); setOpen(false); window.location.assign('https://modelmarket.dev/start'); }}/ >}
  </>;
}
