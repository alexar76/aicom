'use client';

import { TrainFront } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function RailwaySettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, railwayTokenConfigured, handleSettingChange } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <TrainFront className="w-5 h-5 text-violet-400" />
        {t(locale, 'settings.section.railway')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.railway.intro')}</p>
      {!railwayTokenConfigured && (
        <p className="text-xs text-amber-300/90 mb-4 rounded-lg bg-amber-500/10 border border-amber-500/25 px-3 py-2">
          {t(locale, 'settings.railway.tokenWarning')}
        </p>
      )}
      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.railway.recordIntent')}</div>
              <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.railway.recordIntentHelp')}</div>
            </div>
            <button
              type="button"
              onClick={() => handleSettingChange('railway_deploy_enabled', !settings.railway_deploy_enabled)}
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.railway_deploy_enabled ? 'bg-violet-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.railway_deploy_enabled ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>
          <Input
            label={t(locale, 'settings.railway.projectId')}
            placeholder={t(locale, 'settings.railway.projectIdPlaceholder')}
            value={settings.railway_project_id}
            onChange={(e) => handleSettingChange('railway_project_id', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.railway.envName')}
            placeholder={t(locale, 'settings.railway.envNamePlaceholder')}
            value={settings.railway_environment}
            onChange={(e) => handleSettingChange('railway_environment', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.railway.envId')}
            placeholder={t(locale, 'settings.railway.envIdPlaceholder')}
            value={settings.railway_environment_id}
            onChange={(e) => handleSettingChange('railway_environment_id', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.railway.serviceId')}
            placeholder={t(locale, 'settings.railway.serviceIdPlaceholder')}
            value={settings.railway_service_id}
            onChange={(e) => handleSettingChange('railway_service_id', e.target.value)}
          />
        </div>
      )}
    </GlassCard>
  );
}
