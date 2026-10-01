'use client';

import React, { useMemo } from 'react';
import { DollarSign, Info } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

type AgentRow = {
  name: string;
  value?: number;
  calls?: number;
  tokens?: number;
};

type ProductCostRow = {
  name: string;
  product_id?: string;
  state?: string;
  value?: number;
  llm_cost_usd?: number;
  llm_call_count?: number;
  has_llm_data?: boolean;
  agents?: AgentRow[];
};

type HeatmapPayload = {
  value?: number;
  product_count?: number;
  children?: ProductCostRow[];
};

function formatUsd(v: number) {
  if (v <= 0) return '$0.00';
  if (v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

function stateLabel(state: string | undefined, locale: AdminLocale) {
  const s = String(state || '').toUpperCase();
  if (s === 'DEPLOYED_PRODUCTION') return t(locale, 'wow.costHeatmapStateDeployed');
  if (s === 'COMPLETED') return t(locale, 'wow.costHeatmapStateCompleted');
  return state || '—';
}

export function CostOutcomeHeatmap({
  data,
  locale,
}: {
  data: HeatmapPayload | null | undefined;
  locale: AdminLocale;
}) {
  const rows = useMemo(() => data?.children || [], [data?.children]);

  const maxCost = useMemo(
    () => Math.max(0, ...rows.map((r) => Number(r.llm_cost_usd ?? r.value ?? 0))),
    [rows],
  );

  const withSpend = useMemo(
    () => rows.filter((r) => Number(r.llm_cost_usd ?? r.value ?? 0) > 0),
    [rows],
  );

  if (!rows.length) {
    return (
      <GlassCard className="p-4">
        <p className="text-sm text-gray-500">{t(locale, 'wow.costHeatmapEmpty')}</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-emerald-400 shrink-0" />
            {t(locale, 'wow.costHeatmapTitle')}
          </h3>
          <p className="text-xs text-gray-400 leading-relaxed max-w-2xl">{t(locale, 'wow.costHeatmapIntro')}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[10px] uppercase tracking-wide text-gray-500">{t(locale, 'wow.costHeatmapTotal')}</p>
          <p className="text-lg font-semibold text-emerald-400 tabular-nums">{formatUsd(Number(data?.value || 0))}</p>
          <p className="text-[10px] text-gray-500">
            {tVars(locale, 'wow.costHeatmapProductCount', { count: String(rows.length) })}
          </p>
        </div>
      </div>

      {withSpend.length === 0 ? (
        <div className="flex gap-2 rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-100/90">
          <Info className="h-4 w-4 shrink-0 text-amber-300 mt-0.5" />
          <p>{t(locale, 'wow.costHeatmapAllZero')}</p>
        </div>
      ) : null}

      <div className="space-y-2">
        {rows.map((row) => {
          const cost = Number(row.llm_cost_usd ?? row.value ?? 0);
          const calls = Number(row.llm_call_count ?? 0);
          const hasData = row.has_llm_data ?? calls > 0;
          const barPct = maxCost > 0 && cost > 0 ? Math.max(4, (cost / maxCost) * 100) : 0;
          const agents = row.agents || [];

          return (
            <div
              key={row.product_id || row.name}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 space-y-2"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white truncate" title={row.name}>
                    {row.name}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-gray-500">
                    <span className="rounded-full bg-white/5 px-2 py-0.5 text-gray-300">
                      {stateLabel(row.state, locale)}
                    </span>
                    {row.product_id ? (
                      <span className="font-mono text-gray-600">{row.product_id.slice(0, 12)}…</span>
                    ) : null}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-base font-semibold text-white tabular-nums">{formatUsd(cost)}</p>
                  <p className="text-[10px] text-gray-500">
                    {hasData
                      ? tVars(locale, 'wow.costHeatmapCalls', { count: String(calls) })
                      : t(locale, 'wow.costHeatmapNoCalls')}
                  </p>
                </div>
              </div>

              {barPct > 0 ? (
                <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400"
                    style={{ width: `${barPct}%` }}
                  />
                </div>
              ) : null}

              {agents.length > 0 ? (
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {agents.slice(0, 6).map((agent) => (
                    <span
                      key={agent.name}
                      className="rounded-md border border-white/10 bg-slate-900/80 px-2 py-0.5 text-[10px] text-gray-300"
                    >
                      <span className="text-indigo-200">{agent.name}</span>
                      <span className="text-gray-500 mx-1">·</span>
                      <span className="tabular-nums">{formatUsd(Number(agent.value || 0))}</span>
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
