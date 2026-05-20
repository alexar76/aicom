'use client';

import { Palette, Sparkles, BarChart3 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { t, tVars } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function ContentSettings({ api }: { api: SettingsTabApi }) {
  const {
    locale,
    settingsLoading,
    settings,
    referenceTemplatesCatalog,
    refUploadId,
    refUploadTitle,
    refUploadHtml,
    refUploadCss,
    refUploadJs,
    refUploadBusy,
    handleSettingChange,
    setRefUploadId,
    setRefUploadTitle,
    setRefUploadHtml,
    setRefUploadCss,
    setRefUploadJs,
    handleReferenceTemplateUpload,
    handleReferenceTemplateDelete,
    persistAdminSettings,
    adminAutosaveTimerRef,
  } = api;

  const headLen = (settings.published_site_head_html ?? '').length;
  const headHtml = settings.published_site_head_html ?? '';

  return (
    <>
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Palette className="w-5 h-5 text-fuchsia-400" />
          {t(locale, 'settings.section.neuralUi')}
        </h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.neuralUi.intro')}</p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {t(locale, 'settings.loading.short')}
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">{t(locale, 'settings.neuralUi.injectToggle')}</div>
                <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.neuralUi.injectHelp')}</div>
              </div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('reference_templates_enabled', !settings.reference_templates_enabled)
                }
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.reference_templates_enabled ? 'bg-fuchsia-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.reference_templates_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <Input
              label={t(locale, 'settings.neuralUi.templatesDir')}
              placeholder={t(locale, 'settings.neuralUi.templatesDirPlaceholder')}
              value={settings.reference_templates_dir}
              onChange={(e) => handleSettingChange('reference_templates_dir', e.target.value)}
            />
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.selectionMode')}</label>
              <select
                value={settings.reference_template_mode}
                onChange={(e) => handleSettingChange('reference_template_mode', e.target.value)}
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
              >
                <option value="random">{t(locale, 'settings.neuralUi.mode.random')}</option>
                <option value="round_robin">{t(locale, 'settings.neuralUi.mode.roundRobin')}</option>
                <option value="fixed">{t(locale, 'settings.neuralUi.mode.fixed')}</option>
                <option value="match_spec">{t(locale, 'settings.neuralUi.mode.matchSpec')}</option>
              </select>
            </div>
            <p className="text-xs text-gray-500 rounded-lg bg-white/5 px-3 py-2 border border-white/5">
              {t(locale, 'settings.neuralUi.templatesDetected')}{' '}
              <strong className="text-gray-300">{referenceTemplatesCatalog.length}</strong>
              {referenceTemplatesCatalog.length === 0 && settings.reference_templates_enabled ? (
                <span className="text-amber-300/90">{t(locale, 'settings.neuralUi.emptyPoolHint')}</span>
              ) : null}
            </p>

            {referenceTemplatesCatalog.length > 0 && (
              <div className="space-y-2 max-h-52 overflow-y-auto rounded-xl border border-white/10 p-3 bg-black/25">
                <div className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.installedTitle')}</div>
                {referenceTemplatesCatalog.map((tpl) => (
                  <div
                    key={tpl.path}
                    className="flex flex-col gap-2 border-b border-white/5 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between sm:gap-2 sm:py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-white truncate">{tpl.title}</div>
                      <div className="text-[11px] text-gray-500 font-mono truncate">{tpl.path}</div>
                    </div>
                    <button
                      type="button"
                      disabled={refUploadBusy}
                      onClick={() => void handleReferenceTemplateDelete(tpl.path)}
                      className="self-end text-xs text-red-400 hover:text-red-300 disabled:opacity-40 px-2 py-1 rounded-lg hover:bg-red-500/10 sm:self-center"
                    >
                      {t(locale, 'settings.neuralUi.remove')}
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-xl border border-fuchsia-500/25 bg-fuchsia-950/15 p-4 space-y-3">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.neuralUi.addCustomTitle')}</div>
              <p className="text-xs text-gray-400">{t(locale, 'settings.neuralUi.addCustomBody')}</p>
              <Input
                label={t(locale, 'settings.neuralUi.slugLabel')}
                placeholder={t(locale, 'settings.neuralUi.slugPlaceholder')}
                value={refUploadId}
                onChange={(e) => setRefUploadId(e.target.value)}
              />
              <Input
                label={t(locale, 'settings.neuralUi.displayTitle')}
                placeholder={t(locale, 'settings.neuralUi.displayPlaceholder')}
                value={refUploadTitle}
                onChange={(e) => setRefUploadTitle(e.target.value)}
              />
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.indexHtml')}</label>
                <textarea
                  value={refUploadHtml}
                  onChange={(e) => setRefUploadHtml(e.target.value)}
                  rows={8}
                  placeholder={t(locale, 'settings.neuralUi.indexPlaceholder')}
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.styleCss')}</label>
                <textarea
                  value={refUploadCss}
                  onChange={(e) => setRefUploadCss(e.target.value)}
                  rows={5}
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.appJs')}</label>
                <textarea
                  value={refUploadJs}
                  onChange={(e) => setRefUploadJs(e.target.value)}
                  rows={5}
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <Button
                type="button"
                size="sm"
                disabled={refUploadBusy}
                onClick={() => void handleReferenceTemplateUpload()}
              >
                {refUploadBusy ? t(locale, 'settings.modal.saving') : t(locale, 'settings.neuralUi.saveTemplate')}
              </Button>
            </div>

            {settings.reference_template_mode === 'random' && (
              <p className="text-xs text-gray-500">{t(locale, 'settings.neuralUi.hint.random')}</p>
            )}
            {settings.reference_template_mode === 'round_robin' && (
              <p className="text-xs text-gray-500">{t(locale, 'settings.neuralUi.hint.roundRobin')}</p>
            )}
            {settings.reference_template_mode === 'match_spec' && (
              <p className="text-xs text-gray-500">{t(locale, 'settings.neuralUi.hint.matchSpec')}</p>
            )}
            {settings.reference_template_mode === 'fixed' && (
              <div className="space-y-3">
                {referenceTemplatesCatalog.length > 0 ? (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-gray-400">{t(locale, 'settings.neuralUi.templateLabel')}</label>
                    <select
                      value={
                        referenceTemplatesCatalog.some((x) => x.path === settings.reference_template_id)
                          ? settings.reference_template_id
                          : ''
                      }
                      onChange={(e) => handleSettingChange('reference_template_id', e.target.value)}
                      className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
                    >
                      <option value="">{t(locale, 'settings.neuralUi.selectTemplate')}</option>
                      {referenceTemplatesCatalog.map((tpl) => (
                        <option key={tpl.path} value={tpl.path}>
                          {tpl.title} ({tpl.path})
                        </option>
                      ))}
                    </select>
                    {!referenceTemplatesCatalog.some((x) => x.path === settings.reference_template_id) &&
                      settings.reference_template_id.trim() !== '' && (
                        <p className="text-xs text-amber-300/90">
                          {tVars(locale, 'settings.neuralUi.unknownTemplateWarning', {
                            id: settings.reference_template_id,
                          })}
                        </p>
                      )}
                  </div>
                ) : (
                  <Input
                    label={t(locale, 'settings.neuralUi.fixedIdLabel')}
                    placeholder={t(locale, 'settings.neuralUi.fixedIdPlaceholder')}
                    value={settings.reference_template_id}
                    onChange={(e) => handleSettingChange('reference_template_id', e.target.value)}
                  />
                )}
              </div>
            )}
            <div className="flex flex-col gap-2 rounded-xl bg-white/5 p-3 sm:flex-row sm:items-center sm:gap-3">
              <label className="shrink-0 text-sm text-gray-300 sm:whitespace-nowrap">
                {t(locale, 'settings.neuralUi.maxPromptChars')}
              </label>
              <input
                type="number"
                min={2000}
                max={64000}
                step={500}
                value={settings.reference_prompt_max_chars}
                onChange={(e) =>
                  handleSettingChange('reference_prompt_max_chars', parseInt(e.target.value, 10) || 14000)
                }
                className="flex-1 bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
              />
            </div>
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-cyan-400" />
          {t(locale, 'settings.section.publicSite')}
        </h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.publicSite.intro')}</p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {t(locale, 'settings.loading.short')}
          </div>
        ) : (
          <Input
            label={t(locale, 'settings.publicSite.urlLabel')}
            placeholder={t(locale, 'settings.publicSite.urlPlaceholder')}
            value={settings.public_site_url}
            onChange={(e) => handleSettingChange('public_site_url', e.target.value)}
          />
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          {t(locale, 'settings.section.siteBadge')}
        </h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.badge.intro')}</p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {t(locale, 'settings.loading.short')}
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">{t(locale, 'settings.badge.enable')}</div>
                <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.badge.enableHelp')}</div>
              </div>
              <button
                type="button"
                onClick={() => handleSettingChange('site_badge_enabled', !settings.site_badge_enabled)}
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.site_badge_enabled ? 'bg-amber-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.site_badge_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <Input
              label={t(locale, 'settings.badge.urlLabel')}
              placeholder={t(locale, 'settings.badge.urlPlaceholder')}
              value={settings.site_badge_link_url}
              onChange={(e) => handleSettingChange('site_badge_link_url', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-emerald-400" />
          {t(locale, 'settings.section.headSnippet')}
        </h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.headSnippet.intro')}</p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {t(locale, 'settings.loading.short')}
          </div>
        ) : (
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-400" htmlFor="published_site_head_html">
              {t(locale, 'settings.headSnippet.label')}
            </label>
            <textarea
              id="published_site_head_html"
              rows={10}
              spellCheck={false}
              placeholder={t(locale, 'settings.headSnippet.placeholder')}
              value={headHtml}
              onChange={(e) => handleSettingChange('published_site_head_html', e.target.value)}
              onBlur={() => {
                if (adminAutosaveTimerRef.current) {
                  clearTimeout(adminAutosaveTimerRef.current);
                  adminAutosaveTimerRef.current = null;
                }
                void persistAdminSettings();
              }}
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs text-white placeholder:text-gray-600 focus:border-emerald-500/40 focus:outline-none"
            />
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <p className="text-xs text-gray-500 min-w-0">{t(locale, 'settings.headSnippet.footer')}</p>
              <p
                className={`shrink-0 text-xs tabular-nums sm:text-right ${
                  headLen > 100_000 ? 'text-amber-400' : 'text-gray-400'
                }`}
                aria-live="polite"
              >
                {tVars(locale, 'settings.headSnippet.charCount', { n: headLen.toLocaleString() })}
              </p>
            </div>
          </div>
        )}
      </GlassCard>
    </>
  );
}
