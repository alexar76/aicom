'use client';

import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { CHART_COLORS, DARK_CHART_TOOLTIP, usdTooltipFmt } from '@/lib/chartTheme';
import type { ProductPulsePayload } from '../tabs/ProductPulse';
import type { PipelineCatalogProduct } from './PipelineProductList';

const CHART_H = 108;

function qualityPercent(
  economics: Record<string, unknown> | undefined,
  pulse: ProductPulsePayload | undefined,
): number {
  const qs = economics?.quality_score;
  if (typeof qs === 'number' && Number.isFinite(qs)) {
    return Math.min(100, Math.max(0, (qs / 5) * 100));
  }
  const pulseMap: Record<string, number> = { green: 85, amber: 55, red: 25, unknown: 40 };
  if (pulse?.quality_pulse) {
    return pulseMap[pulse.quality_pulse] ?? 40;
  }
  return 0;
}

function deadlinePercent(
  product: PipelineCatalogProduct,
  pulse: ProductPulsePayload | undefined,
  locale: AdminLocale,
): { pct: number; label: string } {
  const state = String(product.state || '').toUpperCase();
  if (state === 'COMPLETED' || state === 'DEPLOYED_PRODUCTION' || state === 'FAILED' || state === 'CANCELLED') {
    return {
      pct: 100,
      label:
        state === 'FAILED'
          ? t(locale, 'pipeline.vitals.deadlineDoneFailed')
          : t(locale, 'pipeline.vitals.deadlineDone'),
    };
  }
  if (pulse?.eta_label) {
    const eta = pulse.eta_seconds;
    if (typeof eta === 'number' && eta > 0) {
      const raw = Number(product.created_at) || 0;
      const createdSec = raw > 1e12 ? raw / 1000 : raw;
      const elapsed = Math.max(0, Date.now() / 1000 - createdSec);
      const pct = Math.min(95, Math.max(5, (elapsed / (elapsed + eta)) * 100));
      return { pct, label: pulse.eta_label };
    }
    return { pct: 50, label: pulse.eta_label };
  }
  return { pct: 35, label: t(locale, 'pipeline.vitals.deadlineUnknown') };
}

function MiniRadial({
  pct,
  fill,
  label,
  sublabel,
}: {
  pct: number;
  fill: string;
  label: string;
  sublabel: string;
}) {
  const data = [{ name: 'v', value: Math.min(100, Math.max(0, pct)), fill }];
  return (
    <div className="flex flex-col items-center">
      <div className="w-full" style={{ height: CHART_H }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%"
            cy="50%"
            innerRadius="62%"
            outerRadius="88%"
            barSize={10}
            data={data}
            startAngle={90}
            endAngle={-270}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="value" cornerRadius={6} background={{ fill: 'rgba(255,255,255,0.06)' }} />
          </RadialBarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] font-medium text-gray-300 -mt-1 text-center">{label}</p>
      <p className="text-[10px] text-gray-500 text-center truncate max-w-full px-1">{sublabel}</p>
    </div>
  );
}

export function PipelineProductVitalsCharts({
  product,
  locale,
}: {
  product: PipelineCatalogProduct;
  locale: AdminLocale;
}) {
  const eco = (product.economics || {}) as Record<string, unknown>;
  const pulse = product.pulse as ProductPulsePayload | undefined;

  const costUsd = Number(eco.llm_cost_usd) || 0;
  const capUsd = Number(eco.pipeline_cost_cap_usd) || 0;
  const costPct = capUsd > 0 ? Math.min(100, (costUsd / capUsd) * 100) : Math.min(100, costUsd * 8);

  const agentBar = useMemo(() => {
    const breakdown = (eco.llm_agent_breakdown || {}) as Record<string, { cost_usd?: number }>;
    return Object.entries(breakdown)
      .map(([name, s]) => ({ name: name.slice(0, 6), cost: Number(s?.cost_usd) || 0 }))
      .filter((r) => r.cost > 0)
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 5);
  }, [eco.llm_agent_breakdown]);

  const { pct: deadlinePct, label: deadlineLabel } = useMemo(
    () => deadlinePercent(product, pulse, locale),
    [product, pulse, locale],
  );
  const qPct = qualityPercent(eco, pulse);
  const qLabel =
    typeof eco.quality_score === 'number'
      ? `${eco.quality_score}/5`
      : pulse?.quality_hint?.slice(0, 28) || t(locale, 'pipeline.vitals.qualityUnknown');

  const costFill = costPct >= 90 ? '#f87171' : costPct >= 70 ? '#fbbf24' : '#34d399';
  const deadlineFill = deadlinePct >= 85 ? '#fbbf24' : '#22d3ee';
  const qualityFill = qPct >= 70 ? '#34d399' : qPct >= 45 ? '#fbbf24' : '#f87171';

  return (
    <div
      className="mb-3 grid grid-cols-1 sm:grid-cols-3 gap-2 rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.04] to-transparent p-2"
      aria-label={t(locale, 'pipeline.vitals.aria')}
    >
      <div className="rounded-lg bg-black/20 p-1.5">
        <p className="text-[9px] uppercase tracking-wider text-gray-500 px-1 mb-0.5">
          {t(locale, 'pipeline.vitals.costTitle')}
        </p>
        {agentBar.length > 0 ? (
          <div style={{ height: CHART_H }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agentBar} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 9 }} interval={0} />
                <YAxis hide domain={[0, 'auto']} />
                <Tooltip formatter={(v: number) => usdTooltipFmt(v)} {...DARK_CHART_TOOLTIP} />
                <Bar dataKey="cost" radius={[3, 3, 0, 0]}>
                  {agentBar.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <MiniRadial
            pct={costPct}
            fill={costFill}
            label={usdTooltipFmt(costUsd)}
            sublabel={
              capUsd > 0
                ? tVars(locale, 'pipeline.vitals.costCap', { cap: capUsd.toFixed(0) })
                : t(locale, 'pipeline.vitals.costNoCap')
            }
          />
        )}
        {agentBar.length > 0 && (
          <p className="text-[10px] text-center text-gray-400 -mt-1">
            {tVars(locale, 'pipeline.vitals.costTotal', { cost: costUsd.toFixed(2) })}
            {capUsd > 0 ? ` · cap $${capUsd.toFixed(0)}` : ''}
          </p>
        )}
      </div>

      <div className="rounded-lg bg-black/20 p-1.5">
        <p className="text-[9px] uppercase tracking-wider text-gray-500 px-1 mb-0.5">
          {t(locale, 'pipeline.vitals.deadlineTitle')}
        </p>
        <MiniRadial pct={deadlinePct} fill={deadlineFill} label={`${Math.round(deadlinePct)}%`} sublabel={deadlineLabel} />
      </div>

      <div className="rounded-lg bg-black/20 p-1.5">
        <p className="text-[9px] uppercase tracking-wider text-gray-500 px-1 mb-0.5">
          {t(locale, 'pipeline.vitals.qualityTitle')}
        </p>
        <MiniRadial pct={qPct} fill={qualityFill} label={`${Math.round(qPct)}%`} sublabel={qLabel} />
      </div>
    </div>
  );
}
