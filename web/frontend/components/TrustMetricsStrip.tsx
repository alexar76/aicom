'use client';

import { useEffect, useState } from 'react';

type TrustMetrics = {
  products_shipped: number;
  products_in_pipeline: number;
  sandbox_sessions_7d: number;
  storefront_views_7d: number;
  leads_7d: number;
  paid_orders_7d: number;
};

export function TrustMetricsStrip() {
  const [m, setM] = useState<TrustMetrics | null>(null);

  useEffect(() => {
    void fetch('/api/marketing/trust-metrics')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setM(d))
      .catch(() => setM(null));
  }, []);

  if (!m) return null;

  const items = [
    { label: 'Products shipped', value: m.products_shipped },
    { label: 'In pipeline', value: m.products_in_pipeline },
    { label: 'Sandbox sessions (7d)', value: m.sandbox_sessions_7d },
    { label: 'Storefront views (7d)', value: m.storefront_views_7d },
  ].filter((x) => x.value > 0);

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap justify-center gap-3 md:gap-6 py-4 px-2">
      {items.map((item) => (
        <div
          key={item.label}
          className="text-center px-4 py-2 rounded-xl bg-white/5 border border-white/10 min-w-[120px]"
        >
          <p className="text-xl md:text-2xl font-bold text-white tabular-nums">{item.value}</p>
          <p className="text-[10px] md:text-xs text-gray-400 uppercase tracking-wide">{item.label}</p>
        </div>
      ))}
    </div>
  );
}
