'use client';

import { Pause, Play } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function FactoryHoldSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange, settingsSaving, publicDemo } = api;
  const onHold = Boolean(settings.factory_on_hold);
  const busy = settingsSaving || settingsLoading;

  const handleToggle = () => {
    if (busy) return;
    handleSettingChange('factory_on_hold', !onHold);
  };

  const statusLabel = onHold
    ? t(locale, 'settings.factoryHold.labelOn')
    : t(locale, 'settings.factoryHold.labelOff');

  return (
    <GlassCard
      className={
        onHold
          ? 'ring-2 ring-amber-400/50 border-amber-500/40 bg-gradient-to-br from-amber-950/40 via-black/40 to-transparent'
          : 'ring-1 ring-emerald-400/30 border-emerald-500/25 bg-gradient-to-br from-emerald-950/20 via-black/20 to-transparent'
      }
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            {onHold ? (
              <Pause className="h-6 w-6 text-amber-400 shrink-0" aria-hidden />
            ) : (
              <Play className="h-6 w-6 text-emerald-400 shrink-0" aria-hidden />
            )}
            <h3 className="text-lg font-semibold text-white">{t(locale, 'settings.factoryHold.title')}</h3>
          </div>
          <p className="text-sm text-gray-300 leading-relaxed">
            {onHold ? t(locale, 'settings.factoryHold.bodyOn') : t(locale, 'settings.factoryHold.bodyOff')}
          </p>
          <p className="mt-2 text-xs text-gray-500">{t(locale, 'settings.factoryHold.hint')}</p>
          {publicDemo ? (
            <p className="mt-1 text-xs text-sky-300/90">{t(locale, 'settings.factoryHold.demoNote')}</p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-3 self-start sm:self-center">
          <span
            className={`min-w-[5.5rem] text-center text-xs font-bold uppercase tracking-wide ${
              onHold ? 'text-amber-300' : 'text-emerald-300'
            }`}
          >
            {statusLabel}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={onHold}
            aria-label={t(locale, onHold ? 'settings.factoryHold.ariaResume' : 'settings.factoryHold.ariaPause')}
            disabled={busy}
            onClick={handleToggle}
            className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${
              onHold ? 'bg-amber-500/80' : 'bg-emerald-600'
            } ${busy ? 'opacity-60 cursor-wait' : 'hover:brightness-110'}`}
          >
            <span
              className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-md transition-transform ${
                onHold ? 'left-0.5' : 'left-[calc(100%-1.625rem)]'
              }`}
            />
          </button>
        </div>
      </div>
    </GlassCard>
  );
}
