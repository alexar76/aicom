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
import { SettingsSection } from '@/components/admin/settings/SettingsSection';
import { SettingsSectionNav } from '@/components/admin/settings/SettingsSectionNav';
import type { AdminLocale } from '@/lib/adminI18n';
import { t } from '@/lib/adminI18n';
import { QualitySettingsCollapsible } from './QualitySettingsCollapsible';
import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';
import { FactoryBackupSettings } from '@/components/admin/settings/FactoryBackupSettings';
import { FactoryHoldSettings } from '@/components/admin/settings/FactoryHoldSettings';
import { HostDiskMonitorSettings } from '@/components/admin/settings/HostDiskMonitorSettings';

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
    <div className="w-full min-w-0 max-w-6xl">
      <header className="mb-6">
        <h2 className="text-xl font-semibold text-white mb-1">{t(locale, 'settings.pageTitle')}</h2>
        <p className="text-sm text-gray-500">{t(locale, 'settings.factoryHold.whereToFind')}</p>
      </header>

      {publicDemo && (
        <p className="text-sm text-sky-200/90 rounded-lg border border-sky-500/40 bg-sky-950/30 p-3 mb-6">
          {t(locale, 'settings.demo.readonlyBanner')}
        </p>
      )}

      <div className="flex flex-col lg:flex-row lg:items-start lg:gap-8 lg:min-h-0">
        <SettingsSectionNav locale={locale} />

        <div className="flex-1 min-w-0 max-w-2xl space-y-6 pb-8">
          <SettingsSection id="factory-hold">
            <FactoryHoldSettings api={api} />
          </SettingsSection>

          <SettingsSection id="director-pipeline">
            <DirectorPipelineSettings api={api} />
          </SettingsSection>

          <SettingsSection id="quality">
            <QualitySettingsCollapsible
              locale={locale}
              open={api.qualityOpen}
              onToggle={() => api.setQualityOpen((v) => !v)}
              quality={api.qualitySettings}
              onChange={(key, value) => api.setQualitySettings((prev) => ({ ...prev, [key]: value }))}
              disabled={api.settingsLoading || api.settingsSaving}
            />
          </SettingsSection>

          <SettingsSection id="director-standup">
            <DirectorStandupSettings api={api} />
          </SettingsSection>

          <SettingsSection id="pipeline-db">
            <PipelineDatabaseSettings
              locale={locale}
              backend={api.settings.pipeline_db_backend}
              databaseUrl={api.settings.pipeline_database_url}
              status={api.pipelineDbStatus as Parameters<typeof PipelineDatabaseSettings>[0]['status']}
              disabled={api.settingsLoading || api.settingsSaving}
              onBackendChange={(v) => api.handleSettingChange('pipeline_db_backend', v)}
              onDatabaseUrlChange={(v) => api.handleSettingChange('pipeline_database_url', v)}
            />
          </SettingsSection>

          <SettingsSection id="git-remote">
            <GitRemoteSettings api={api} />
          </SettingsSection>

          <SettingsSection id="docker">
            <DockerRegistrySettings api={api} />
          </SettingsSection>

          <SettingsSection id="auto-publish">
            <AutoPublishSettings api={api} />
          </SettingsSection>

          <SettingsSection id="railway">
            <RailwaySettings api={api} />
          </SettingsSection>

          <SettingsSection id="content">
            <ContentSettings api={api} />
          </SettingsSection>

          <SettingsSection id="telegram">
            <TelegramSettings api={api} />
          </SettingsSection>

          <SettingsSection id="host-disk">
            <HostDiskMonitorSettings api={api} />
          </SettingsSection>

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

          <SettingsSection id="factory-backup">
            <FactoryBackupSettings locale={locale} />
          </SettingsSection>

          <SettingsSection id="account-security">
            <AccountSecuritySettings api={api} publicDemo={publicDemo} />
          </SettingsSection>

          <SettingsSection id="demo-replay">
            <DemoReplayMonitorSection variant="settings" />
          </SettingsSection>

          <SettingsSection id="theme">
            <ThemeSettings api={api} />
          </SettingsSection>
        </div>
      </div>
    </div>
  );
}
