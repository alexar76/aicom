'use client';

import { Container } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function DockerRegistrySettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Container className="w-5 h-5 text-blue-400" />
        {t(locale, 'settings.section.docker')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.docker.intro')}</p>

      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          <Input
            label={t(locale, 'settings.docker.registryUrl')}
            placeholder={t(locale, 'settings.docker.registryPlaceholder')}
            value={settings.docker_registry}
            onChange={(e) => handleSettingChange('docker_registry', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.docker.username')}
            placeholder={t(locale, 'settings.docker.usernamePlaceholder')}
            value={settings.docker_username}
            onChange={(e) => handleSettingChange('docker_username', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.docker.password')}
            type="password"
            placeholder={t(locale, 'settings.docker.passwordPlaceholder')}
            value={settings.docker_password}
            onChange={(e) => handleSettingChange('docker_password', e.target.value)}
          />
        </div>
      )}
    </GlassCard>
  );
}
