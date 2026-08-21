'use client';

import { Pause } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { t, type AdminLocale } from '@/lib/adminI18n';

export function FactoryHoldBanner({
  locale,
  onOpenSettings,
}: {
  locale: AdminLocale;
  onOpenSettings: () => void;
}) {
  return (
    <GlassCard className="mb-6 border border-amber-500/40 bg-amber-950/30 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <Pause className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" aria-hidden />
          <p className="text-sm text-amber-100/95 leading-relaxed">
            {t(locale, 'settings.factoryHold.globalBannerOn')}
          </p>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-50 hover:bg-amber-500/25"
          onClick={onOpenSettings}
        >
          {t(locale, 'settings.factoryHold.openSettings')}
        </button>
      </div>
    </GlassCard>
  );
}
