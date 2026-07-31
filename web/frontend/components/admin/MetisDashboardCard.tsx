'use client';

import { useEffect, useState } from 'react';
import { BrainCircuit, Loader2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

type MetisStatusPayload = {
  status: 'active' | 'inactive';
  ecosystem: {
    deployed: boolean;
    url: string;
    health: {
      status?: string;
      version?: string;
      knowledge_entries?: number;
      cluster_nodes?: number;
    } | null;
  };
  factory: {
    gate_mode: string;
    gate_enabled: boolean;
    uses_metis: boolean;
    gate_blocking: boolean;
    gate_stages: string[];
    gate_route: string;
    min_score: string;
  };
  usage: {
    total_products: number;
    checked: number;
    approved: number;
    flagged: number;
    pending: number;
    avg_verify_score: number | null;
    last_checked_at: number | null;
  };
};

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${
        active ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.65)]' : 'bg-gray-500'
      }`}
      aria-hidden
    />
  );
}

export function MetisDashboardCard({ locale }: { locale: AdminLocale }) {
  const [data, setData] = useState<MetisStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetch('/api/admin/metis/status', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setData(d))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <GlassCard>
        <p className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden />
          {t(locale, 'dashboard.metis.loading')}
        </p>
      </GlassCard>
    );
  }

  if (!data) return null;

  const active = data.status === 'active';
  const usage = data.usage;
  const health = data.ecosystem.health;

  return (
    <GlassCard className="border border-emerald-500/20 bg-emerald-500/[0.03]">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
            <span
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center text-emerald-400"
              aria-hidden
            >
              <BrainCircuit className="h-6 w-6" strokeWidth={2} />
            </span>
            {t(locale, 'dashboard.metis.title')}
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-gray-400">{t(locale, 'dashboard.metis.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/25 px-3 py-1.5 text-sm">
          <StatusDot active={active} />
          <span className={active ? 'text-emerald-300' : 'text-gray-400'}>
            {t(locale, active ? 'dashboard.metis.statusActive' : 'dashboard.metis.statusInactive')}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {[
          [t(locale, 'dashboard.metis.metricDeployed'), data.ecosystem.deployed ? t(locale, 'dashboard.metis.yes') : t(locale, 'dashboard.metis.no')],
          [t(locale, 'dashboard.metis.metricFactory'), data.factory.uses_metis ? t(locale, 'dashboard.metis.yes') : t(locale, 'dashboard.metis.no')],
          [t(locale, 'dashboard.metis.metricApproved'), String(usage.approved)],
          [t(locale, 'dashboard.metis.metricFlagged'), String(usage.flagged)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg bg-black/30 px-3 py-2">
            <p className="text-lg font-bold text-white tabular-nums">{val}</p>
            <p className="text-[10px] uppercase tracking-wide text-gray-500">{label}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-gray-400">
        <span>
          {t(locale, 'dashboard.metis.gateMode')}:{' '}
          <span className="text-gray-200">{data.factory.gate_mode}</span>
        </span>
        <span>
          {t(locale, 'dashboard.metis.stages')}:{' '}
          <span className="text-gray-200">{data.factory.gate_stages.join(', ')}</span>
        </span>
        {health?.version ? (
          <span>
            {t(locale, 'dashboard.metis.version')}:{' '}
            <span className="text-gray-200">{health.version}</span>
          </span>
        ) : null}
        {typeof health?.knowledge_entries === 'number' ? (
          <span>
            {t(locale, 'dashboard.metis.knowledge')}:{' '}
            <span className="text-gray-200">{health.knowledge_entries}</span>
          </span>
        ) : null}
        {usage.avg_verify_score != null ? (
          <span>
            {t(locale, 'dashboard.metis.avgScore')}:{' '}
            <span className="text-gray-200">{usage.avg_verify_score.toFixed(2)}</span>
          </span>
        ) : null}
        <span>
          {tVars(locale, 'dashboard.metis.pending', { n: usage.pending, total: usage.total_products })}
        </span>
      </div>
    </GlassCard>
  );
}
