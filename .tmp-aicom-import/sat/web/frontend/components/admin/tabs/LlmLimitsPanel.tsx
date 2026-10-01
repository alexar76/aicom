'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Gauge, Loader2, Network, RefreshCw, Save, Shield } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api, { LlmLimitsPanelData } from '@/lib/api';
import { AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

function capPct(spent: number, cap: number): number {
  if (cap <= 0) return 0;
  return Math.min(100, (spent / cap) * 100);
}

export function LlmLimitsPanel({ locale }: { locale: AdminLocale }) {
  const [data, setData] = useState<LlmLimitsPanelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    max_requests_per_minute: '0',
    daily_cost_cap_usd: '0',
    monthly_cost_cap_usd: '0',
    pre_call_reserve_usd: '0.05',
    critical_escalation_enabled: false,
  });

  const applyPanel = useCallback((panel: LlmLimitsPanelData) => {
    setData(panel);
    const saved = panel.limits_saved;
    setDraft({
      max_requests_per_minute: String(saved.max_requests_per_minute ?? 0),
      daily_cost_cap_usd: String(saved.daily_cost_cap_usd ?? 0),
      monthly_cost_cap_usd: String(saved.monthly_cost_cap_usd ?? 0),
      pre_call_reserve_usd: String(saved.pre_call_reserve_usd ?? 0.05),
      critical_escalation_enabled: Boolean(saved.critical_escalation_enabled),
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applyPanel(await api.getLlmLimits());
    } catch (e) {
      console.error(e);
      toast.error(t(locale, 'providers.limits.toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [applyPanel, locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      applyPanel(
        await api.updateLlmLimits({
          max_requests_per_minute: parseInt(draft.max_requests_per_minute, 10) || 0,
          daily_cost_cap_usd: parseFloat(draft.daily_cost_cap_usd) || 0,
          monthly_cost_cap_usd: parseFloat(draft.monthly_cost_cap_usd) || 0,
          pre_call_reserve_usd: parseFloat(draft.pre_call_reserve_usd) || 0,
          critical_escalation_enabled: draft.critical_escalation_enabled,
        })
      );
      toast.success(t(locale, 'providers.limits.toast.saved'));
    } catch (e) {
      console.error(e);
      toast.error(t(locale, 'providers.limits.toast.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const usage = data?.usage;
  const effective = data?.limits_effective;
  const envOverrides = data?.env_overrides ?? {};

  return (
    <GlassCard className="border border-indigo-500/20">
      <div className="mb-4 flex items-center gap-2">
        <Shield className="h-5 w-5 text-amber-400" />
        <h3 className="text-base font-semibold text-white">{t(locale, 'providers.limits.title')}</h3>
      </div>

      <div className="space-y-4">
        <p className="text-xs leading-relaxed text-gray-400">
          {t(locale, 'providers.limits.intro.beforeZero')}{' '}
          <strong className="font-medium text-gray-300">0</strong>
          {t(locale, 'providers.limits.intro.afterZero')}
          <code className="text-[10px] text-gray-500">AIFACTORY_LLM_*</code>
          {t(locale, 'providers.limits.intro.afterEnv')}
        </p>

        {loading && !data ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t(locale, 'providers.limits.loading')}
          </div>
        ) : (
          <>
            {usage && effective ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <UsageStat
                  locale={locale}
                  label={t(locale, 'providers.limits.stat.today')}
                  spent={usage.day_spend_usd}
                  cap={effective.daily_cost_cap_usd}
                />
                <UsageStat
                  locale={locale}
                  label={t(locale, 'providers.limits.stat.month')}
                  spent={usage.month_spend_usd}
                  cap={effective.monthly_cost_cap_usd}
                />
                <StatBox title={t(locale, 'providers.limits.stat.requests')}>
                  {usage.requests_last_minute}
                  {effective.max_requests_per_minute > 0 ? (
                    <span className="text-gray-500"> / {effective.max_requests_per_minute}</span>
                  ) : null}
                </StatBox>
                <StatBox title={t(locale, 'providers.limits.stat.preCallReserve')}>
                  ${effective.pre_call_reserve_usd.toFixed(4)}
                </StatBox>
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <LimitField
                locale={locale}
                label={t(locale, 'providers.limits.field.maxRpm.label')}
                hint={t(locale, 'providers.limits.field.maxRpm.hint')}
                value={draft.max_requests_per_minute}
                envLocked={envOverrides.max_requests_per_minute}
                onChange={(v) => setDraft((d) => ({ ...d, max_requests_per_minute: v }))}
              />
              <LimitField
                locale={locale}
                label={t(locale, 'providers.limits.field.dailyCap.label')}
                hint={t(locale, 'providers.limits.field.dailyCap.hint')}
                value={draft.daily_cost_cap_usd}
                envLocked={envOverrides.daily_cost_cap_usd}
                onChange={(v) => setDraft((d) => ({ ...d, daily_cost_cap_usd: v }))}
              />
              <LimitField
                locale={locale}
                label={t(locale, 'providers.limits.field.monthlyCap.label')}
                hint={t(locale, 'providers.limits.field.monthlyCap.hint')}
                value={draft.monthly_cost_cap_usd}
                envLocked={envOverrides.monthly_cost_cap_usd}
                onChange={(v) => setDraft((d) => ({ ...d, monthly_cost_cap_usd: v }))}
              />
              <LimitField
                locale={locale}
                label={t(locale, 'providers.limits.field.preCallReserve.label')}
                hint={t(locale, 'providers.limits.field.preCallReserve.hint')}
                value={draft.pre_call_reserve_usd}
                envLocked={envOverrides.pre_call_reserve_usd}
                onChange={(v) => setDraft((d) => ({ ...d, pre_call_reserve_usd: v }))}
              />
            </div>

            <EscalationToggle
              locale={locale}
              enabled={draft.critical_escalation_enabled}
              envLocked={envOverrides.critical_escalation_enabled}
              onChange={(v) => setDraft((d) => ({ ...d, critical_escalation_enabled: v }))}
            />

            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => void handleSave()} disabled={saving || loading}>
                {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                {t(locale, 'providers.limits.btn.save')}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading || saving}>
                <RefreshCw className="mr-1 h-4 w-4" />
                {t(locale, 'providers.limits.btn.refreshUsage')}
              </Button>
            </div>
          </>
        )}
      </div>
    </GlassCard>
  );
}

function StatBox({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-black/30 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{title}</div>
      <div className="mt-1 font-mono text-sm text-white">{children}</div>
    </div>
  );
}

function UsageStat({
  locale,
  label,
  spent,
  cap,
}: {
  locale: AdminLocale;
  label: string;
  spent: number;
  cap: number;
}) {
  const pct = capPct(spent, cap);
  const over = cap > 0 && spent >= cap;
  return (
    <div className="rounded-lg bg-black/30 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-1 font-mono text-sm">
        <span className={over ? 'text-red-400' : 'text-white'}>${spent.toFixed(4)}</span>
        {cap > 0 ? (
          <span className="text-gray-500">/ ${cap.toFixed(2)}</span>
        ) : (
          <span className="text-gray-600">{t(locale, 'providers.limits.noCap')}</span>
        )}
      </div>
      {cap > 0 ? (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full rounded-full transition-all ${over ? 'bg-red-500' : 'bg-emerald-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function EscalationToggle({
  locale,
  enabled,
  envLocked,
  onChange,
}: {
  locale: AdminLocale;
  enabled: boolean;
  envLocked?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="rounded-lg border border-indigo-500/20 bg-black/20 p-3">
      <div className="flex items-start justify-between gap-3">
        <label className="flex items-center gap-1.5 text-xs font-medium text-gray-200">
          <Network className="h-3.5 w-3.5 text-indigo-400" />
          {t(locale, 'providers.limits.escalation.title')}
          {envLocked ? (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
              {t(locale, 'providers.limits.envBadge')}
            </span>
          ) : null}
        </label>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          disabled={envLocked}
          onClick={() => onChange(!enabled)}
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
            enabled ? 'bg-indigo-500' : 'bg-white/15'
          } ${envLocked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              enabled ? 'translate-x-4' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-gray-400">
        <strong className="font-medium text-gray-300">{t(locale, 'providers.limits.escalation.offLabel')}</strong>{' '}
        {t(locale, 'providers.limits.escalation.offBeforeDefault')}{' '}
        <code className="text-[10px] text-gray-500">default_provider</code>{' '}
        {t(locale, 'providers.limits.escalation.offAfterDefault')}{' '}
        <code className="text-[10px] text-gray-500">fallback_provider</code>,{' '}
        {t(locale, 'providers.limits.escalation.offAfterFallback')}
      </p>
      <p className="mt-1.5 text-[11px] leading-relaxed text-gray-400">
        <strong className="font-medium text-gray-300">{t(locale, 'providers.limits.escalation.onLabel')}</strong>{' '}
        {t(locale, 'providers.limits.escalation.onBeforeCritical')}{' '}
        {t(locale, 'providers.limits.escalation.criticalTasks')}{' '}
        <strong className="text-gray-300">{t(locale, 'providers.limits.escalation.onToAnother')}</strong>{' '}
        {t(locale, 'providers.limits.escalation.onAfterAnother')}{' '}
        <strong className="text-gray-300">{t(locale, 'providers.limits.escalation.betweenProviders')}</strong>
        {t(locale, 'providers.limits.escalation.onTailBeforeEnv')}
        <code className="text-[10px] text-gray-500">{t(locale, 'providers.limits.escalation.envVar')}</code>
        {t(locale, 'providers.limits.escalation.onTailAfterEnv')}
      </p>
    </div>
  );
}

function LimitField({
  locale,
  label,
  hint,
  value,
  envLocked,
  onChange,
}: {
  locale: AdminLocale;
  label: string;
  hint: string;
  value: string;
  envLocked?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 flex items-center gap-1 text-xs font-medium text-gray-300">
        <Gauge className="h-3 w-3 text-gray-500" />
        {label}
        {envLocked ? (
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
            {t(locale, 'providers.limits.envBadge')}
          </span>
        ) : null}
      </label>
      <Input
        type="number"
        min={0}
        step="any"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="font-mono text-sm"
        disabled={envLocked}
      />
      <p className="mt-1 text-[10px] text-gray-500">{hint}</p>
    </div>
  );
}
