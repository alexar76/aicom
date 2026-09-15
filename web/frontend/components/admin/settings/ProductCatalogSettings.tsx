'use client';

import { Package } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function ProductCatalogSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange, githubPatConfigured } = api;
  const ghReady = Boolean(githubPatConfigured);

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Package className="w-5 h-5 text-sky-400" />
        {t(locale, 'settings.section.productCatalog')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.productCatalog.intro')}</p>
      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          {!ghReady && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              {t(locale, 'settings.productCatalog.patMissing')}
            </p>
          )}
          <label
            className={`flex flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors sm:flex-row sm:items-center sm:justify-between ${
              ghReady ? 'cursor-pointer hover:bg-white/10' : 'cursor-not-allowed opacity-60'
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.productCatalog.enable')}</div>
              <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.productCatalog.enableHelp')}</div>
            </div>
            <button
              type="button"
              disabled={!ghReady}
              onClick={() => {
                if (!ghReady) return;
                handleSettingChange('product_catalog_enabled', !settings.product_catalog_enabled);
              }}
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.product_catalog_enabled && ghReady ? 'bg-sky-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.product_catalog_enabled && ghReady ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>
          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">
                {t(locale, 'settings.productCatalog.requireHouse')}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {t(locale, 'settings.productCatalog.requireHouseHelp')}
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                handleSettingChange(
                  'product_catalog_require_github_house',
                  !settings.product_catalog_require_github_house
                )
              }
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.product_catalog_require_github_house ? 'bg-sky-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.product_catalog_require_github_house ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>
          <Input
            label={t(locale, 'settings.productCatalog.allowlist')}
            placeholder={t(locale, 'settings.productCatalog.allowlistPlaceholder')}
            value={settings.product_catalog_allowlist}
            onChange={(e) => handleSettingChange('product_catalog_allowlist', e.target.value)}
          />
          <p className="text-xs text-gray-500">{t(locale, 'settings.productCatalog.remoteHint')}</p>
        </div>
      )}
    </GlassCard>
  );
}
