'use client';

import { Bot, UserCheck } from 'lucide-react';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

/** Nested sub-block under Autonomous development — only shown when auto_pipeline is on. */
export function AutonomyModeSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange, autonomyModeSaving, publicDemo } = api;
  const full = settings.autonomy_mode === 'full';
  const busy = autonomyModeSaving || settingsLoading;

  const handleToggle = () => {
    if (busy) return;
    handleSettingChange('autonomy_mode', full ? 'supervised' : 'full');
  };

  return (
    <div
      className={`rounded-xl border p-3 transition-colors ${
        full
          ? 'border-violet-500/30 bg-violet-950/20'
          : 'border-white/10 bg-white/[0.03]'
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            {full ? (
              <Bot className="h-5 w-5 shrink-0 text-violet-400" aria-hidden />
            ) : (
              <UserCheck className="h-5 w-5 shrink-0 text-slate-400" aria-hidden />
            )}
            <div className="text-sm font-medium text-white">{t(locale, 'settings.autonomyMode.title')}</div>
          </div>
          <p className="text-xs leading-relaxed text-gray-400">
            {full ? t(locale, 'settings.autonomyMode.bodyFull') : t(locale, 'settings.autonomyMode.bodySupervised')}
          </p>
          <p className="mt-1.5 text-[11px] text-gray-500">{t(locale, 'settings.autonomyMode.hint')}</p>
          {publicDemo ? (
            <p className="mt-1 text-[11px] text-sky-300/90">{t(locale, 'settings.autonomyMode.demoNote')}</p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-3 self-start sm:self-center">
          <span
            className={`min-w-[5.5rem] text-center text-[10px] font-bold uppercase tracking-wide ${
              full ? 'text-violet-300' : 'text-slate-400'
            }`}
          >
            {full ? t(locale, 'settings.autonomyMode.labelFull') : t(locale, 'settings.autonomyMode.labelSupervised')}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={full}
            aria-label={t(locale, full ? 'settings.autonomyMode.ariaSupervised' : 'settings.autonomyMode.ariaFull')}
            disabled={busy}
            onClick={handleToggle}
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
              full ? 'bg-violet-600' : 'bg-white/20'
            } ${busy ? 'cursor-wait opacity-60' : 'hover:brightness-110'}`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
                full ? 'left-[calc(100%-1.375rem)]' : 'left-0.5'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
}
