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
import {
  computePipelineProductVitals,
  formatVitalsPercent,
  formatVitalsUsd,
} from '@/lib/pipelineProductVitals';
import { agentCostBarLabel } from '@/lib/pipelineProductHelpers';
import type { PipelineCatalogProduct } from './PipelineProductList';

const CHART_H = 108;

function MiniRadial({
  pct,
  fill,
  label,
  sublabel,
  empty,
}: {
  pct: number | null;
  fill: string;
  label: string;
  sublabel: string;
  empty?: boolean;
}) {
  const value = empty || pct == null ? 0 : Math.min(100, Math.max(0, pct));
  const data = [{ name: 'v', value, fill }];
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
  const vitals = useMemo(() => computePipelineProductVitals(product, locale), [product, locale]);
  const eco = (product.economics || {}) as Record<string, unknown>;

  const agentBar = useMemo(() => {
    const breakdown = (eco.llm_agent_breakdown || {}) as Record<string, { cost_usd?: number }>;
    return Object.entries(breakdown)
      .map(([name, s]) => ({ name: agentCostBarLabel(name), cost: Number(s?.cost_usd) || 0 }))
      .filter((r) => r.cost > 0)
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 5);
  }, [eco.llm_agent_breakdown]);

  const costFill =
    vitals.costPct != null && vitals.costPct >= 90
      ? '#f87171'
      : vitals.costPct != null && vitals.costPct >= 70
        ? '#fbbf24'
        : '#34d399';
  const progressFill =
    vitals.progressPct != null && vitals.progressPct >= 85 ? '#fbbf24' : '#22d3ee';
  const qualityFill =
    vitals.qualityPct == null
      ? '#64748b'
      : vitals.qualityPct >= 70
        ? '#34d399'
        : vitals.qualityPct >= 45
          ? '#fbbf24'
          : '#f87171';

  const costRadialPct = vitals.costPct ?? (vitals.costUsd > 0 ? 100 : null);
  const costLabel = formatVitalsUsd(vitals.costUsd);
  const costSublabel =
    vitals.costCapUsd > 0
      ? tVars(locale, 'pipeline.vitals.costCap', { cap: vitals.costCapUsd.toFixed(0) })
      : vitals.costUsd > 0
        ? vitals.costDetail
        : t(locale, 'pipeline.vitals.costNoCap');

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
            pct={costRadialPct}
            fill={costFill}
            label={costLabel}
            sublabel={costSublabel}
            empty={vitals.costUsd <= 0 && vitals.costPct == null}
          />
        )}
        {agentBar.length > 0 && (
          <p className="text-[10px] text-center text-gray-400 -mt-1">
            {tVars(locale, 'pipeline.vitals.costTotal', { cost: vitals.costUsd.toFixed(2) })}
            {vitals.costCapUsd > 0 ? ` · cap $${vitals.costCapUsd.toFixed(0)}` : ''}
          </p>
        )}
      </div>

      <div className="rounded-lg bg-black/20 p-1.5">
        <p className="text-[9px] uppercase tracking-wider text-gray-500 px-1 mb-0.5">
          {t(locale, 'pipeline.vitals.progressTitle')}
        </p>
        <MiniRadial
          pct={vitals.progressPct}
          fill={progressFill}
          label={formatVitalsPercent(vitals.progressPct)}
          sublabel={vitals.progressDetail}
          empty={vitals.progressPct == null}
        />
      </div>

      <div className="rounded-lg bg-black/20 p-1.5">
        <p className="text-[9px] uppercase tracking-wider text-gray-500 px-1 mb-0.5">
          {t(locale, 'pipeline.vitals.qualityTitle')}
        </p>
        <MiniRadial
          pct={vitals.qualityPct}
          fill={qualityFill}
          label={formatVitalsPercent(vitals.qualityPct)}
          sublabel={vitals.qualityDetail}
          empty={vitals.qualityPct == null}
        />
      </div>
    </div>
  );
}
