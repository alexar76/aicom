'use client';

import { Crosshair } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { t, tVars, type AdminLocale } from '@/lib/adminI18n';

export function PipelineFocusBanner({
  locale,
  focusProductId,
  pausedCount,
  onOpenPipeline,
}: {
  locale: AdminLocale;
  focusProductId: string;
  pausedCount: number;
  onOpenPipeline: () => void;
}) {
  return (
    <GlassCard className="mb-6 border border-indigo-500/40 bg-indigo-950/30 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <Crosshair className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm text-indigo-100/95 leading-relaxed">
              {tVars(locale, 'pipeline.focus.globalBanner', {
                productId: focusProductId,
                paused: pausedCount,
              })}
            </p>
            <p className="mt-1 font-mono text-[11px] text-indigo-200/80 truncate">{focusProductId}</p>
          </div>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-xs font-medium text-indigo-50 hover:bg-indigo-500/25"
          onClick={onOpenPipeline}
        >
          {t(locale, 'pipeline.focus.openPipeline')}
        </button>
      </div>
    </GlassCard>
  );
}
