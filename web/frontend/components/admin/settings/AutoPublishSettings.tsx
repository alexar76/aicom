'use client';

import { Globe } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function AutoPublishSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Globe className="w-5 h-5 text-emerald-400" />
        {t(locale, 'settings.section.autoPublish')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.autoPublish.intro')}</p>
      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.autoPublish.enable')}</div>
              <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.autoPublish.enableHelp')}</div>
            </div>
            <button
              type="button"
              onClick={() => handleSettingChange('auto_publish_enabled', !settings.auto_publish_enabled)}
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.auto_publish_enabled ? 'bg-emerald-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.auto_publish_enabled ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t(locale, 'settings.autoPublish.provider')}</label>
            <select
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
              value={settings.auto_publish_provider}
              onChange={(e) => handleSettingChange('auto_publish_provider', e.target.value)}
            >
              <option value="none">{t(locale, 'settings.autoPublish.provider.none')}</option>
              <option value="vercel">{t(locale, 'settings.autoPublish.provider.vercel')}</option>
              <option value="netlify">{t(locale, 'settings.autoPublish.provider.netlify')}</option>
              <option value="cloudflare_pages">{t(locale, 'settings.autoPublish.provider.cloudflare')}</option>
            </select>
          </div>
          <Input
            label={t(locale, 'settings.autoPublish.netlifySiteId')}
            placeholder={t(locale, 'settings.autoPublish.netlifyPlaceholder')}
            value={settings.auto_publish_netlify_site_id}
            onChange={(e) => handleSettingChange('auto_publish_netlify_site_id', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.autoPublish.cfProject')}
            placeholder={t(locale, 'settings.autoPublish.cfPlaceholder')}
            value={settings.auto_publish_cf_project_name}
            onChange={(e) => handleSettingChange('auto_publish_cf_project_name', e.target.value)}
          />
        </div>
      )}
    </GlassCard>
  );
}
