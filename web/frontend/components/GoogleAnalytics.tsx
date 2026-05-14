'use client';

import { useEffect, useState } from 'react';
import Script from 'next/script';

function gaIdFromBuildEnv(): string | null {
  const v = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  if (typeof v !== 'string') return null;
  const t = v.trim();
  if (!/^G-[A-Za-z0-9]{4,32}$/i.test(t)) return null;
  return t.toUpperCase();
}

/**
 * GA4 on the Next.js storefront. Build-time env wins; otherwise loads measurement id from
 * ``GET /api/marketing/ga-measurement-id`` (parsed from Admin → head snippet for generated sites).
 */
export function GoogleAnalytics() {
  const [id, setId] = useState<string | null>(() => gaIdFromBuildEnv());

  useEffect(() => {
    if (id) return;
    const ac = new AbortController();
    (async () => {
      try {
        const res = await fetch('/api/marketing/ga-measurement-id', {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'no-store',
          signal: ac.signal,
        });
        if (!res.ok) return;
        const data = (await res.json()) as { measurement_id?: string | null };
        const mid = typeof data.measurement_id === 'string' ? data.measurement_id.trim() : '';
        if (mid && /^G-[A-Za-z0-9]{4,32}$/i.test(mid)) {
          setId(mid.toUpperCase());
        }
      } catch {
        /* ignore */
      }
    })();
    return () => ac.abort();
  }, [id]);

  if (!id) return null;

  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`}
        strategy="afterInteractive"
      />
      <Script id="ga4-init" strategy="afterInteractive">
        {`
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${id}');
        `.trim()}
      </Script>
    </>
  );
}
