'use client';

import { Zap, Loader2, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { t, tVars } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';
import { AutonomyModeSettings } from './AutonomyModeSettings';

export function DirectorPipelineSettings({ api }: { api: SettingsTabApi }) {
  const {
    locale,
    settingsLoading,
    settings,
    publicDemo,
    throughputEffective,
    throughputSnapshotBusy,
    autoGenModalOpen,
    autoGenIntervalDraft,
    autoGenSaving,
    directorTriggering,
    directorMessage,
    handleSettingChange,
    handleAutoPipelineToggleClick,
    handleAutoGenConfirm,
    closeAutoGenModal,
    setAutoGenIntervalDraft,
    refreshThroughputSnapshotOnly,
    clampAutoPipelineMinutes,
    handleTriggerDirector,
  } = api;

  const turboLabel = throughputEffective
    ? t(
        locale,
        throughputEffective.local_high_throughput_enabled ? 'settings.throughput.on' : 'settings.throughput.off',
      )
    : '';

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
        <Zap className="w-5 h-5 text-yellow-400" />
        {t(locale, 'settings.section.directorPipeline')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.director.intro')}</p>

      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          {t(locale, 'settings.loading.short')}
        </div>
      ) : (
        <div className="space-y-4">
          <label
            className={`flex flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors sm:flex-row sm:items-center sm:justify-between ${
              publicDemo && !settings.auto_pipeline
                ? 'cursor-pointer hover:bg-white/10 ring-1 ring-amber-500/30'
                : 'cursor-pointer hover:bg-white/10'
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white">{t(locale, 'settings.toggle.autonomousDev')}</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {publicDemo && !settings.auto_pipeline
                  ? t(locale, 'settings.demo.autoGenToggleHint')
                  : t(locale, 'settings.toggle.autonomousDev.help')}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void handleAutoPipelineToggleClick()}
              disabled={autoGenSaving || settingsLoading}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 ${
                settings.auto_pipeline ? 'bg-indigo-500' : 'bg-white/20'
              } ${autoGenSaving ? 'opacity-60 cursor-wait' : ''}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                  settings.auto_pipeline ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </label>

          {settings.auto_pipeline && (
            <div className="ml-1 border-l-2 border-indigo-500/30 pl-3">
              <p className="mb-2 text-[11px] text-gray-500">{t(locale, 'settings.autonomyMode.requiresAutoDev')}</p>
              <AutonomyModeSettings api={api} />
            </div>
          )}

          {settings.auto_pipeline && (
            <p className="text-xs text-gray-500 px-1">
              {tVars(locale, 'settings.director.cadence', {
                minutes: String(settings.auto_pipeline_interval_minutes),
              })}
            </p>
          )}

          <div className="flex flex-col gap-2 p-3 rounded-xl bg-white/5">
            <label className="text-sm text-gray-300">{t(locale, 'settings.director.minIntervalLabel')}</label>
            <div className="flex flex-wrap gap-2">
              {[15, 30, 60, 360, 720, 1440].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => handleSettingChange('auto_pipeline_interval_minutes', m)}
                  className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
                    settings.auto_pipeline_interval_minutes === m
                      ? 'border-indigo-400 bg-indigo-500/20 text-white'
                      : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10'
                  }`}
                >
                  {m >= 1440 ? '24h' : m >= 60 ? `${m / 60}h` : `${m}m`}
                </button>
              ))}
            </div>
            <input
              type="number"
              min={15}
              max={10080}
              value={settings.auto_pipeline_interval_minutes}
              onChange={(e) =>
                handleSettingChange(
                  'auto_pipeline_interval_minutes',
                  clampAutoPipelineMinutes(parseInt(e.target.value, 10) || 60),
                )
              }
              className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500/50"
            />
            <p className="text-xs text-gray-500">{t(locale, 'settings.director.intervalHint')}</p>
          </div>

          <div className="border-t border-white/5 pt-4 space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">{t(locale, 'settings.toggle.pipelineCostOptimized')}</div>
                <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.toggle.pipelineCostOptimized.help')}</div>
              </div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('pipeline_cost_optimized', !(settings.pipeline_cost_optimized ?? true))
                }
                className={`relative h-6 w-12 shrink-0 rounded-full transition-colors ${
                  (settings.pipeline_cost_optimized ?? true) ? 'bg-indigo-500' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
                    (settings.pipeline_cost_optimized ?? true) ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">{t(locale, 'settings.toggle.highThroughput')}</div>
                <div className="text-xs text-gray-400 mt-0.5">{t(locale, 'settings.toggle.highThroughput.help')}</div>
              </div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('local_high_throughput_enabled', !settings.local_high_throughput_enabled)
                }
                className={`relative h-6 w-12 shrink-0 rounded-full transition-colors ${
                  settings.local_high_throughput_enabled ? 'bg-emerald-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
                    settings.local_high_throughput_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <div className="mt-3 rounded-lg border border-white/10 bg-black/25 px-3 py-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-gray-300">{t(locale, 'settings.throughput.title')}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={throughputSnapshotBusy || settingsLoading}
                  onClick={() => void refreshThroughputSnapshotOnly()}
                  className="inline-flex h-8 items-center gap-1.5 px-2 text-xs text-gray-300 hover:text-white"
                >
                  {throughputSnapshotBusy ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5 shrink-0" aria-hidden />
                  )}
                  {t(locale, 'settings.btn.refresh')}
                </Button>
              </div>
              <p className="mb-2 text-[11px] leading-snug text-gray-500">{t(locale, 'settings.throughput.envHint')}</p>
              {throughputEffective ? (
                <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.turboPreset')}</dt>
                    <dd className="font-mono text-gray-200">{turboLabel}</dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.maxRunningTasks')}</dt>
                    <dd className="font-mono text-gray-200">{throughputEffective.effective_max_running_tasks}</dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.taskExecutorConcurrency')}</dt>
                    <dd className="font-mono text-gray-200">{throughputEffective.effective_task_executor_concurrency}</dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.batchStartsPerCycle')}</dt>
                    <dd className="font-mono text-gray-200">
                      {throughputEffective.effective_batch_pipeline_max_start_per_cycle}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.batchActiveCeiling')}</dt>
                    <dd className="font-mono text-gray-200">{throughputEffective.effective_batch_pipeline_active_limit}</dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.llmMaxParallel')}</dt>
                    <dd className="font-mono text-gray-200">{throughputEffective.effective_llm_max_parallel_requests}</dd>
                  </div>
                  <div className="flex justify-between gap-3 sm:col-span-2">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.llmMinIntervalSec')}</dt>
                    <dd className="font-mono text-gray-200">
                      {Number(throughputEffective.effective_llm_min_interval_sec).toFixed(3)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.llmMaxRpm')}</dt>
                    <dd className="font-mono text-gray-200">
                      {throughputEffective.effective_llm_max_requests_per_minute ?? 0}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.llmDailyCapUsd')}</dt>
                    <dd className="font-mono text-gray-200">
                      {throughputEffective.effective_llm_daily_cost_cap_usd ?? 0}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                    <dt className="text-gray-500">{t(locale, 'settings.throughput.llmMonthlyCapUsd')}</dt>
                    <dd className="font-mono text-gray-200">
                      {throughputEffective.effective_llm_monthly_cost_cap_usd ?? 0}
                    </dd>
                  </div>
                </dl>
              ) : !settingsLoading ? (
                <p className="text-xs text-gray-500">{t(locale, 'settings.throughput.snapshotUnavailable')}</p>
              ) : null}
            </div>
          </div>

          <Modal
            isOpen={autoGenModalOpen}
            onClose={closeAutoGenModal}
            title={t(locale, 'settings.autogenModal.title')}
            size="md"
          >
            {publicDemo ? (
              <div
                role="alert"
                className="mb-4 rounded-xl border border-amber-500/50 bg-amber-950/40 px-4 py-3 text-sm leading-relaxed text-amber-100"
              >
                <p className="font-semibold text-amber-200 mb-1.5">
                  {t(locale, 'settings.demo.autoGenModalTitle')}
                </p>
                <p>{t(locale, 'settings.demo.autoGenModalBanner')}</p>
              </div>
            ) : (
              <p className="text-sm text-gray-300 mb-4">{t(locale, 'settings.autogenModal.body')}</p>
            )}
            <div className={`flex flex-wrap gap-2 mb-4 ${publicDemo ? 'pointer-events-none opacity-50' : ''}`}>
              {(
                [
                  ['settings.autogenModal.preset15m', 15],
                  ['settings.autogenModal.preset30m', 30],
                  ['settings.autogenModal.preset1h', 60],
                  ['settings.autogenModal.preset6h', 360],
                  ['settings.autogenModal.preset12h', 720],
                  ['settings.autogenModal.preset24h', 1440],
                ] as const
              ).map(([labelKey, m]) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setAutoGenIntervalDraft(m)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    autoGenIntervalDraft === m
                      ? 'border-indigo-400 bg-indigo-500/25 text-white'
                      : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10'
                  }`}
                >
                  {t(locale, labelKey)}
                </button>
              ))}
            </div>
            <label className={`block text-xs text-gray-400 mb-1 ${publicDemo ? 'opacity-50' : ''}`}>
              {t(locale, 'settings.label.customIntervalMinutes')}
            </label>
            <input
              type="number"
              min={15}
              max={10080}
              value={autoGenIntervalDraft}
              disabled={publicDemo}
              onChange={(e) =>
                setAutoGenIntervalDraft(clampAutoPipelineMinutes(parseInt(e.target.value, 10) || 60))
              }
              className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white mb-4 focus:outline-none focus:border-indigo-500/50 disabled:cursor-not-allowed disabled:opacity-50"
            />
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                size="sm"
                variant="ghost"
                onClick={closeAutoGenModal}
                className="w-full sm:w-auto"
              >
                {autoGenSaving
                  ? t(locale, 'settings.modal.cancelSaving')
                  : publicDemo
                    ? t(locale, 'settings.modal.close')
                    : t(locale, 'settings.modal.cancel')}
              </Button>
              {!publicDemo ? (
                <Button
                  size="sm"
                  onClick={() => void handleAutoGenConfirm()}
                  disabled={autoGenSaving}
                  className="w-full sm:w-auto"
                >
                  {autoGenSaving ? t(locale, 'settings.modal.saving') : t(locale, 'settings.modal.enable')}
                </Button>
              ) : null}
            </div>
          </Modal>

          <div className="border-t border-white/5 pt-4">
            <p className="text-xs text-gray-500 mb-2">{t(locale, 'settings.directorManualHint')}</p>
            <Button size="sm" onClick={() => void handleTriggerDirector()} disabled={directorTriggering}>
              {directorTriggering ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {t(locale, 'settings.director.triggering')}
                </span>
              ) : (
                t(locale, 'settings.btn.triggerDirector')
              )}
            </Button>
            {directorMessage && <p className="text-xs mt-2 text-gray-400">{directorMessage}</p>}
          </div>
        </div>
      )}
    </GlassCard>
  );
}
