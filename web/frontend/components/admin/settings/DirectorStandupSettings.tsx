'use client';

import { Clock } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function DirectorStandupSettings({ api }: { api: SettingsTabApi }) {
  const { locale, corpChatSettings, corpChatSaving, setCorpChatSettings } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Clock className="w-5 h-5 text-cyan-400" />
        {t(locale, 'settings.section.directorStandup')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.standup.intro')}</p>
      <div className="space-y-4 max-w-md">
        <label className="flex cursor-pointer items-start gap-3 sm:items-center">
          <input
            type="checkbox"
            checked={corpChatSettings.director_standup_enabled}
            onChange={(e) =>
              setCorpChatSettings((prev) => ({ ...prev, director_standup_enabled: e.target.checked }))
            }
            className="rounded border-white/20"
          />
          <span className="text-sm text-gray-300">{t(locale, 'settings.standup.enableDaily')}</span>
        </label>
        <Input
          label={t(locale, 'settings.standup.localTime')}
          placeholder="09:30"
          value={corpChatSettings.director_standup_time}
          onChange={(e) => setCorpChatSettings((prev) => ({ ...prev, director_standup_time: e.target.value }))}
        />
        <Input
          label={t(locale, 'settings.standup.timezone')}
          placeholder="UTC"
          value={corpChatSettings.director_standup_timezone}
          onChange={(e) =>
            setCorpChatSettings((prev) => ({ ...prev, director_standup_timezone: e.target.value }))
          }
        />
        <p className="text-[11px] text-gray-500">
          {corpChatSaving ? t(locale, 'settings.standup.saving') : t(locale, 'settings.standup.autosaveHint')}
        </p>
      </div>
    </GlassCard>
  );
}
