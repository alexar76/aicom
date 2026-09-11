'use client';

import { HardDrive } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t, tVars, type AdminLocale } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

type DiskLive = {
  level?: string;
  paths?: Array<{ path: string; used_pct: number; free_gb: number; level?: string }>;
};

function liveLevelLabel(locale: AdminLocale, level: string | undefined): string {
  const u = String(level || 'ok').toLowerCase();
  if (u === 'critical') return t(locale, 'settings.hostDisk.liveCritical');
  if (u === 'warning') return t(locale, 'settings.hostDisk.liveWarning');
  return t(locale, 'settings.hostDisk.liveOk');
}

function liveBadgeClass(level: string | undefined): string {
  const u = String(level || 'ok').toLowerCase();
  if (u === 'critical') return 'border-red-500/40 bg-red-950/40 text-red-200';
  if (u === 'warning') return 'border-amber-500/40 bg-amber-950/40 text-amber-200';
  return 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200';
}

export function HostDiskMonitorSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange, publicDemo, diskMonitorLive } = api;

  const live = (diskMonitorLive || {}) as DiskLive;

  const numField = (
    key:
      | 'disk_warn_used_pct'
      | 'disk_crit_used_pct'
      | 'disk_warn_free_gb'
      | 'disk_crit_free_gb'
      | 'disk_alert_cooldown_hours'
      | 'disk_monitor_interval_minutes',
    label: string,
    step = '1',
  ) => (
    <Input
      label={label}
      type="number"
      step={step}
      min={0}
      disabled={settingsLoading || publicDemo}
      value={String(settings[key] ?? '')}
      onChange={(e) => {
        const n = parseFloat(e.target.value);
        if (Number.isFinite(n)) handleSettingChange(key, n);
      }}
    />
  );

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-2 flex items-center gap-2">
        <HardDrive className="w-5 h-5 text-purple-400" />
        {t(locale, 'settings.section.hostDisk')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.hostDisk.intro')}</p>

      {diskMonitorLive ? (
        <div className="mb-4 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">
            {t(locale, 'settings.hostDisk.liveTitle')}
          </p>
          <span
            className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase ${liveBadgeClass(live.level)}`}
          >
            {liveLevelLabel(locale, live.level)}
          </span>
          <ul className="mt-2 space-y-1 text-xs text-gray-400">
            {(live.paths || []).map((p) => (
              <li key={p.path}>
                {tVars(locale, 'settings.hostDisk.pathLine', {
                  path: p.path,
                  used: String(p.used_pct),
                  free: String(p.free_gb),
                })}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-gray-500">{t(locale, 'settings.hostDisk.envOverride')}</p>
        </div>
      ) : null}

      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          …
        </div>
      ) : (
        <div className="space-y-4">
          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.hostDisk.telegramToggle')}</div>
              <p className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.hostDisk.telegramHelp')}</p>
            </div>
            <button
              type="button"
              disabled={publicDemo}
              onClick={() =>
                handleSettingChange('telegram_notify_host_disk', !settings.telegram_notify_host_disk)
              }
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.telegram_notify_host_disk ? 'bg-purple-600' : 'bg-white/20'
              } ${publicDemo ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.telegram_notify_host_disk ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            {numField('disk_warn_used_pct', t(locale, 'settings.hostDisk.warnUsedPct'))}
            {numField('disk_crit_used_pct', t(locale, 'settings.hostDisk.critUsedPct'))}
            {numField('disk_warn_free_gb', t(locale, 'settings.hostDisk.warnFreeGb'), '0.1')}
            {numField('disk_crit_free_gb', t(locale, 'settings.hostDisk.critFreeGb'), '0.1')}
            {numField('disk_alert_cooldown_hours', t(locale, 'settings.hostDisk.cooldownHours'), '0.5')}
            {numField('disk_monitor_interval_minutes', t(locale, 'settings.hostDisk.intervalMinutes'), '1')}
          </div>
        </div>
      )}
    </GlassCard>
  );
}
