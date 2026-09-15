'use client';

import React, { useMemo } from 'react';
import { GlassCard } from '@/components/ui/GlassCard';
import { type AdminLocale, t } from '@/lib/adminI18n';
import {
  computePipelineProductVitals,
  formatVitalsPercent,
  formatVitalsUsd,
} from '@/lib/pipelineProductVitals';
import type { PipelineCatalogProduct } from './PipelineProductList';

export function PipelineProductVitalsTable({
  products,
  locale,
}: {
  products: PipelineCatalogProduct[];
  locale: AdminLocale;
}) {
  const rows = useMemo(
    () => products.map((p) => computePipelineProductVitals(p, locale)),
    [products, locale],
  );

  if (rows.length === 0) return null;

  return (
    <GlassCard hover={false} className="mb-4 overflow-hidden border border-white/10">
      <div className="px-3 py-2 border-b border-white/10">
        <h3 className="text-sm font-semibold text-white">{t(locale, 'pipeline.vitals.tableTitle')}</h3>
        <p className="text-xs text-gray-500 mt-0.5">{t(locale, 'pipeline.vitals.tableHint')}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-white/10">
              <th className="px-3 py-2 font-medium">{t(locale, 'pipeline.vitals.colProduct')}</th>
              <th className="px-3 py-2 font-medium">{t(locale, 'pipeline.vitals.colState')}</th>
              <th className="px-3 py-2 font-medium text-right">{t(locale, 'pipeline.vitals.colCost')}</th>
              <th className="px-3 py-2 font-medium text-right">{t(locale, 'pipeline.vitals.colProgress')}</th>
              <th className="px-3 py-2 font-medium text-right">{t(locale, 'pipeline.vitals.colQuality')}</th>
              <th className="px-3 py-2 font-medium">{t(locale, 'pipeline.vitals.colNotes')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.productId} className="border-b border-white/5 hover:bg-white/[0.03]">
                <td className="px-3 py-2 text-gray-200 max-w-[12rem] truncate" title={r.productLabel}>
                  {r.productLabel}
                  <div className="font-mono text-[10px] text-gray-600 truncate">{r.productId}</div>
                </td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.state}</td>
                <td className="px-3 py-2 text-right tabular-nums text-emerald-300/90">
                  {formatVitalsUsd(r.costUsd)}
                  {r.costCapUsd > 0 && r.costPct != null ? (
                    <div className="text-[10px] text-gray-500">
                      {formatVitalsPercent(r.costPct)} {t(locale, 'pipeline.vitals.ofCap')}
                    </div>
                  ) : (
                    <div className="text-[10px] text-gray-500 truncate max-w-[8rem] ml-auto">{r.costDetail}</div>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-cyan-300/90">
                  {formatVitalsPercent(r.progressPct)}
                  {r.completedStages != null && r.totalStages != null ? (
                    <div className="text-[10px] text-gray-500">
                      {r.completedStages}/{r.totalStages}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-amber-200/90">
                  {formatVitalsPercent(r.qualityPct)}
                  <div className="text-[10px] text-gray-500">{r.qualitySource}</div>
                </td>
                <td className="px-3 py-2 text-gray-500 max-w-[14rem]">
                  <div className="truncate" title={r.progressDetail}>
                    {r.progressDetail}
                  </div>
                  <div className="truncate" title={r.qualityDetail}>
                    {r.qualityDetail}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}
