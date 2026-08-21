'use client';

import { useEffect, useState } from 'react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Loader2 } from 'lucide-react';

type FunnelDashboard = {
  metrics: {
    stages: Record<string, number>;
    leads_submitted: number;
    pipeline: { completed: number; in_progress: number; failed: number };
    rates: { sandbox_from_product_view_pct?: number; paid_from_checkout_click_pct?: number | null };
  };
  recent_leads: Array<{ email: string; status: string; product_id?: string; source?: string }>;
};

export function FunnelDashboardCard() {
  const [data, setData] = useState<FunnelDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetch('/api/admin/funnel/dashboard?window_hours=168', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setData(d))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <GlassCard>
        <p className="text-sm text-gray-500 flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading funnel…
        </p>
      </GlassCard>
    );
  }

  if (!data) return null;

  const s = data.metrics.stages || {};
  const p = data.metrics.pipeline || { completed: 0, in_progress: 0, failed: 0 };

  return (
    <GlassCard className="border border-violet-500/25 bg-violet-500/[0.04]">
      <h3 className="text-lg font-semibold text-white mb-1">Growth funnel (7d)</h3>
      <p className="text-sm text-gray-400 mb-4">Visit → view → sandbox → checkout → paid</p>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center mb-4">
        {[
          ['Views', s.page_view || 0],
          ['Product', s.product_view || 0],
          ['Sandbox', s.sandbox_click || 0],
          ['Checkout', s.checkout_click || 0],
          ['Paid', s.paid || 0],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg bg-black/30 py-2 px-1">
            <p className="text-lg font-bold text-white tabular-nums">{val}</p>
            <p className="text-[10px] text-gray-500 uppercase">{label}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-gray-400">
        <span>Leads: {data.metrics.leads_submitted || 0}</span>
        <span>Shipped: {p.completed}</span>
        <span>In pipeline: {p.in_progress}</span>
        {data.metrics.rates?.sandbox_from_product_view_pct != null && (
          <span>Sandbox rate: {data.metrics.rates.sandbox_from_product_view_pct}%</span>
        )}
      </div>
    </GlassCard>
  );
}
