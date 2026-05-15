'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Gauge, Loader2, RefreshCw, Save, Shield } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api, { LlmLimitsPanelData } from '@/lib/api';
import toast from 'react-hot-toast';

function capPct(spent: number, cap: number): number {
  if (cap <= 0) return 0;
  return Math.min(100, (spent / cap) * 100);
}

export function LlmLimitsPanel() {
  const [data, setData] = useState<LlmLimitsPanelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    max_requests_per_minute: '0',
    daily_cost_cap_usd: '0',
    monthly_cost_cap_usd: '0',
    pre_call_reserve_usd: '0.05',
  });

  const applyPanel = useCallback((panel: LlmLimitsPanelData) => {
    setData(panel);
    const saved = panel.limits_saved;
    setDraft({
      max_requests_per_minute: String(saved.max_requests_per_minute ?? 0),
      daily_cost_cap_usd: String(saved.daily_cost_cap_usd ?? 0),
      monthly_cost_cap_usd: String(saved.monthly_cost_cap_usd ?? 0),
      pre_call_reserve_usd: String(saved.pre_call_reserve_usd ?? 0.05),
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applyPanel(await api.getLlmLimits());
    } catch (e) {
      console.error(e);
      toast.error('Failed to load LLM limits');
    } finally {
      setLoading(false);
    }
  }, [applyPanel]);

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
        })
      );
      toast.success('LLM limits saved');
    } catch (e) {
      console.error(e);
      toast.error('Failed to save LLM limits');
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
        <h3 className="text-base font-semibold text-white">Cost caps &amp; rate limits</h3>
      </div>

      <div className="space-y-4">
        <p className="text-xs leading-relaxed text-gray-400">
          Enforced in the LLM router before each call. <strong className="font-medium text-gray-300">0</strong> disables a
          cap. Non-empty <code className="text-[10px] text-gray-500">AIFACTORY_LLM_*</code> env vars override saved YAML.
        </p>

        {loading && !data ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : (
          <>
            {usage && effective ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <UsageStat label="Today (UTC)" spent={usage.day_spend_usd} cap={effective.daily_cost_cap_usd} />
                <UsageStat label="This month (UTC)" spent={usage.month_spend_usd} cap={effective.monthly_cost_cap_usd} />
                <StatBox title="Requests / last 60s">
                  {usage.requests_last_minute}
                  {effective.max_requests_per_minute > 0 ? (
                    <span className="text-gray-500"> / {effective.max_requests_per_minute}</span>
                  ) : null}
                </StatBox>
                <StatBox title="Pre-call reserve">${effective.pre_call_reserve_usd.toFixed(4)}</StatBox>
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <LimitField
                label="Max requests / minute"
                hint="Rolling 60s window; router waits when full"
                value={draft.max_requests_per_minute}
                envLocked={envOverrides.max_requests_per_minute}
                onChange={(v) => setDraft((d) => ({ ...d, max_requests_per_minute: v }))}
              />
              <LimitField
                label="Daily cost cap (USD)"
                hint="Estimated spend from llm_calls.jsonl"
                value={draft.daily_cost_cap_usd}
                envLocked={envOverrides.daily_cost_cap_usd}
                onChange={(v) => setDraft((d) => ({ ...d, daily_cost_cap_usd: v }))}
              />
              <LimitField
                label="Monthly cost cap (USD)"
                hint="Resets on UTC month boundary"
                value={draft.monthly_cost_cap_usd}
                envLocked={envOverrides.monthly_cost_cap_usd}
                onChange={(v) => setDraft((d) => ({ ...d, monthly_cost_cap_usd: v }))}
              />
              <LimitField
                label="Pre-call reserve (USD)"
                hint="Pessimistic hold before token usage is known"
                value={draft.pre_call_reserve_usd}
                envLocked={envOverrides.pre_call_reserve_usd}
                onChange={(v) => setDraft((d) => ({ ...d, pre_call_reserve_usd: v }))}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => void handleSave()} disabled={saving || loading}>
                {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                Save limits
              </Button>
              <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading || saving}>
                <RefreshCw className="mr-1 h-4 w-4" />
                Refresh usage
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

function UsageStat({ label, spent, cap }: { label: string; spent: number; cap: number }) {
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
          <span className="text-gray-600">(no cap)</span>
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

function LimitField({
  label,
  hint,
  value,
  envLocked,
  onChange,
}: {
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
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">env</span>
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
