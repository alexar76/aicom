'use client';

import { GitBranch } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function GitRemoteSettings({ api }: { api: SettingsTabApi }) {
  const { locale, settingsLoading, settings, handleSettingChange } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <GitBranch className="w-5 h-5 text-orange-400" />
        {t(locale, 'settings.section.gitRemote')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.git.intro')}</p>

      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          <Input
            label={t(locale, 'settings.git.remoteUrl')}
            placeholder={t(locale, 'settings.git.remoteUrlPlaceholder')}
            value={settings.git_remote_url}
            onChange={(e) => handleSettingChange('git_remote_url', e.target.value)}
          />
          <Input
            label={t(locale, 'settings.git.defaultBranch')}
            placeholder="main"
            value={settings.git_default_branch}
            onChange={(e) => handleSettingChange('git_default_branch', e.target.value)}
          />
        </div>
      )}
    </GlassCard>
  );
}
