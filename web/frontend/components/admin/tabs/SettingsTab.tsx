'use client';

import { useEffect, useState } from 'react';
import apiClient from '@/lib/api';
import { PipelineDatabaseSettings } from '@/components/admin/settings/PipelineDatabaseSettings';
import { DirectorPipelineSettings } from '@/components/admin/settings/DirectorPipelineSettings';
import { DirectorStandupSettings } from '@/components/admin/settings/DirectorStandupSettings';
import { GitRemoteSettings } from '@/components/admin/settings/GitRemoteSettings';
import { DockerRegistrySettings } from '@/components/admin/settings/DockerRegistrySettings';
import { AutoPublishSettings } from '@/components/admin/settings/AutoPublishSettings';
import { RailwaySettings } from '@/components/admin/settings/RailwaySettings';
import { ContentSettings } from '@/components/admin/settings/ContentSettings';
import { TelegramSettings } from '@/components/admin/settings/TelegramSettings';
import {
  AccountSecuritySettings,
  ThemeSettings,
} from '@/components/admin/settings/AccountSecuritySettings';
import { useSettingsTabState } from '@/components/admin/settings/useSettingsTabState';
import type { AdminLocale } from '@/lib/adminI18n';
import { t } from '@/lib/adminI18n';
import { QualitySettingsCollapsible } from './QualitySettingsCollapsible';
import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';
import { FactoryBackupSettings } from '@/components/admin/settings/FactoryBackupSettings';

export function SettingsTab({ locale }: { locale: AdminLocale }) {
  const api = useSettingsTabState(locale);
  const [publicDemo, setPublicDemo] = useState(false);

  useEffect(() => {
    void apiClient
      .getMe()
      .then((me) => setPublicDemo(Boolean(me.public_demo || me.public_demo_readonly)))
      .catch(() => setPublicDemo(false));
  }, []);

  return (
    <div className="w-full min-w-0 max-w-2xl space-y-6">
      <h2 className="text-xl font-semibold text-white mb-4">{t(locale, 'settings.pageTitle')}</h2>

      {publicDemo && (
        <p className="text-sm text-sky-200/90 rounded-lg border border-sky-500/40 bg-sky-950/30 p-3">
          {t(locale, 'settings.demo.readonlyBanner')}
        </p>
      )}

      <DirectorPipelineSettings api={api} />

      <QualitySettingsCollapsible
        locale={locale}
        open={api.qualityOpen}
        onToggle={() => api.setQualityOpen((v) => !v)}
        quality={api.qualitySettings}
        onChange={(key, value) => api.setQualitySettings((prev) => ({ ...prev, [key]: value }))}
        disabled={api.settingsLoading || api.settingsSaving}
      />

      <DirectorStandupSettings api={api} />

      <PipelineDatabaseSettings
        locale={locale}
        backend={api.settings.pipeline_db_backend}
        databaseUrl={api.settings.pipeline_database_url}
        status={api.pipelineDbStatus as Parameters<typeof PipelineDatabaseSettings>[0]['status']}
        disabled={api.settingsLoading || api.settingsSaving}
        onBackendChange={(v) => api.handleSettingChange('pipeline_db_backend', v)}
        onDatabaseUrlChange={(v) => api.handleSettingChange('pipeline_database_url', v)}
      />

      <GitRemoteSettings api={api} />
      <DockerRegistrySettings api={api} />
      <AutoPublishSettings api={api} />
      <RailwaySettings api={api} />
      <ContentSettings api={api} />
      <TelegramSettings api={api} />

      {!publicDemo && !api.settingsLoading && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex items-center gap-2 text-sm">
            {api.settingsSaving ? (
              <span className="flex items-center gap-2 text-gray-300">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                {t(locale, 'settings.persist.saving')}
              </span>
            ) : (
              <span className="text-emerald-400/90">{t(locale, 'settings.persist.hint')}</span>
            )}
          </div>
          {api.settingsMessage && (
            <span className="text-sm text-gray-400 break-words">{api.settingsMessage}</span>
          )}
        </div>
      )}

      <FactoryBackupSettings locale={locale} />
      <AccountSecuritySettings api={api} publicDemo={publicDemo} />
      <DemoReplayMonitorSection variant="settings" />
      <ThemeSettings api={api} />
    </div>
  );
}
