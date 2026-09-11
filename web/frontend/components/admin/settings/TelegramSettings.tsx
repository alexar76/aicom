'use client';

import { Send } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function TelegramSettings({ api }: { api: SettingsTabApi }) {
  const {
    locale,
    settingsLoading,
    settings,
    telegramBotTokenConfigured,
    telegramBotTokenInput,
    telegramTestBusy,
    handleSettingChange,
    setTelegramBotTokenInput,
    handleTestTelegram,
    handleRevokeTelegramToken,
  } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Send className="w-5 h-5 text-sky-400" />
        {t(locale, 'settings.section.telegram')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.telegram.intro')}</p>
      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.telegram')}
        </div>
      ) : (
        <div className="space-y-4">
          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.telegram.enable')}</div>
              <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.telegram.enableHelp')}</div>
            </div>
            <button
              type="button"
              onClick={() => handleSettingChange('telegram_notify_enabled', !settings.telegram_notify_enabled)}
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.telegram_notify_enabled ? 'bg-sky-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.telegram_notify_enabled ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>

          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1 text-sm text-gray-300">{t(locale, 'settings.telegram.notifyStages')}</div>
            <button
              type="button"
              onClick={() =>
                handleSettingChange('telegram_notify_pipeline_stages', !settings.telegram_notify_pipeline_stages)
              }
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.telegram_notify_pipeline_stages ? 'bg-sky-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.telegram_notify_pipeline_stages ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>

          <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1 text-sm text-gray-300">{t(locale, 'settings.telegram.notifyProducts')}</div>
            <button
              type="button"
              onClick={() =>
                handleSettingChange('telegram_notify_new_products', !settings.telegram_notify_new_products)
              }
              className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                settings.telegram_notify_new_products ? 'bg-sky-600' : 'bg-white/20'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.telegram_notify_new_products ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>

          <Input
            label={t(locale, 'settings.telegram.chatId')}
            placeholder={t(locale, 'settings.telegram.chatIdPlaceholder')}
            value={settings.telegram_chat_id}
            onChange={(e) => handleSettingChange('telegram_chat_id', e.target.value)}
          />

          <div>
            <label className="text-xs text-gray-500 block mb-1">{t(locale, 'settings.telegram.botTokenLabel')}</label>
            <Input
              label=""
              type="password"
              placeholder={
                telegramBotTokenConfigured
                  ? t(locale, 'settings.telegram.botTokenPlaceholderKeep')
                  : t(locale, 'settings.telegram.botTokenPlaceholderNew')
              }
              value={telegramBotTokenInput}
              onChange={(e) => setTelegramBotTokenInput(e.target.value)}
            />
            <p className="text-[11px] text-gray-500 mt-1">
              {t(locale, 'settings.telegram.tokenHint')}
              {telegramBotTokenConfigured ? (
                <span className="text-emerald-400/90"> {t(locale, 'settings.telegram.tokenStored')}</span>
              ) : (
                <span className="text-amber-400/90"> {t(locale, 'settings.telegram.notConfigured')}</span>
              )}
            </p>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={telegramTestBusy}
              onClick={() => void handleTestTelegram()}
            >
              {telegramTestBusy ? t(locale, 'settings.telegram.sending') : t(locale, 'settings.telegram.sendTest')}
            </Button>
            {telegramBotTokenConfigured && (
              <Button type="button" variant="ghost" size="sm" onClick={() => void handleRevokeTelegramToken()}>
                {t(locale, 'settings.telegram.removeToken')}
              </Button>
            )}
          </div>
        </div>
      )}
    </GlassCard>
  );
}
