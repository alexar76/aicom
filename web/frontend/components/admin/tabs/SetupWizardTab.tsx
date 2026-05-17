'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Link2,
  PartyPopper,
  Rocket,
  Sparkles,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api, { type CreateProviderPayload } from '@/lib/api';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

const STORAGE_DONE = 'aicom_admin_setup_wizard_done_v1';
/** Dispatched on `window` when the user marks the setup checklist complete (same tab). */
export const SETUP_WIZARD_DONE_EVENT = 'aicom-setup-wizard-done';

type PresetId = 'deepseek_api' | 'anthropic_cloud' | 'groq_api';

const PRESET_DESC_KEY: Record<PresetId, string> = {
  deepseek_api: 'setup.preset.deepseek.desc',
  anthropic_cloud: 'setup.preset.anthropic.desc',
  groq_api: 'setup.preset.groq.desc',
};

const PRESETS: Record<
  PresetId,
  Omit<CreateProviderPayload, 'api_key'> & { label: string }
> = {
  deepseek_api: {
    label: 'DeepSeek',
    name: 'deepseek_api',
    provider_type: 'openai_compatible',
    base_url: 'https://api.deepseek.com/v1',
    api_key_env: null,
    enabled: true,
    models: { heavy: 'deepseek-reasoner', light: 'deepseek-chat' },
    capabilities: {
      context_window: 128000,
      max_tokens: 32000,
      supports_vision: false,
      supports_streaming: true,
    },
    priority: 10,
    health_check_endpoint: '/v1/models',
  },
  anthropic_cloud: {
    label: 'Anthropic',
    name: 'anthropic_cloud',
    provider_type: 'anthropic',
    base_url: 'https://api.anthropic.com/v1',
    api_key_env: null,
    enabled: true,
    models: {
      heavy: 'claude-3-5-sonnet-latest',
      light: 'claude-3-5-haiku-latest',
    },
    capabilities: {
      context_window: 200000,
      max_tokens: 8192,
      supports_vision: true,
      supports_streaming: true,
    },
    priority: 8,
    health_check_endpoint: '/v1/models',
  },
  groq_api: {
    label: 'Groq',
    name: 'groq_api',
    provider_type: 'openai_compatible',
    base_url: 'https://api.groq.com/openai/v1',
    api_key_env: null,
    enabled: true,
    models: {
      heavy: 'llama3-70b-8192',
      light: 'llama3-8b-8192',
    },
    capabilities: {
      context_window: 8192,
      max_tokens: 4096,
      supports_vision: false,
      supports_streaming: true,
    },
    priority: 4,
    health_check_endpoint: '/v1/models',
  },
};

function canSaveProviders(role: string | null | undefined): boolean {
  if (!role) return true;
  const r = role.toLowerCase();
  return r === 'admin' || r === 'super_admin';
}

export function SetupWizardTab({
  adminRole,
  locale,
}: {
  adminRole: string | null;
  locale: AdminLocale;
}) {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [origin, setOrigin] = useState('');
  const [providerNames, setProviderNames] = useState<Set<string>>(new Set());
  const [preset, setPreset] = useState<PresetId>('deepseek_api');
  const [apiKey, setApiKey] = useState('');
  const [makeDefault, setMakeDefault] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [markedDone, setMarkedDone] = useState(false);

  const allowSave = useMemo(() => canSaveProviders(adminRole), [adminRole]);

  const loadProviderNames = useCallback(async () => {
    try {
      const list = await api.getProviders();
      setProviderNames(new Set(list.map((p) => p.name)));
    } catch {
      setProviderNames(new Set());
    }
  }, []);

  useEffect(() => {
    setOrigin(typeof window !== 'undefined' ? window.location.origin : '');
    void loadProviderNames();
    try {
      setMarkedDone(localStorage.getItem(STORAGE_DONE) === '1');
    } catch {
      setMarkedDone(false);
    }
  }, [loadProviderNames]);

  const markComplete = () => {
    try {
      localStorage.setItem(STORAGE_DONE, '1');
    } catch {
      /* ignore */
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(SETUP_WIZARD_DONE_EVENT));
    }
    setMarkedDone(true);
    toast.success(t(locale, 'setup.toast.marked'));
  };

  const saveProviderStep = async () => {
    if (!allowSave) {
      toast.error(t(locale, 'setup.toast.noRole'));
      return;
    }
    const base = PRESETS[preset];
    const key = apiKey.trim();
    if (!key) {
      toast.error(t(locale, 'setup.toast.needKey'));
      return;
    }
    setSaving(true);
    try {
      const payload: CreateProviderPayload = {
        name: base.name,
        provider_type: base.provider_type,
        base_url: base.base_url,
        api_key: key,
        api_key_env: null,
        enabled: true,
        models: base.models,
        capabilities: base.capabilities,
        priority: base.priority,
        health_check_endpoint: base.health_check_endpoint,
      };
      if (providerNames.has(base.name)) {
        const { name: _n, ...updateBody } = payload;
        await api.updateProvider(base.name, updateBody);
        toast.success(tVars(locale, 'setup.toast.updated', { label: base.label }));
      } else {
        await api.createProvider(payload);
        toast.success(tVars(locale, 'setup.toast.added', { label: base.label }));
      }
      if (makeDefault) {
        await api.setDefaultProvider(base.name);
        toast.success(tVars(locale, 'setup.toast.defaultSet', { name: base.name }));
      }
      await loadProviderNames();
      setStep(4);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const runQuickTest = async () => {
    const name = PRESETS[preset].name;
    setTesting(true);
    try {
      const r = await api.testProvider(name, 'light');
      if (r.success) {
        toast.success(
          tVars(locale, 'setup.toast.testOk', {
            ms: r.latency_ms,
            model: r.model || '—',
          }),
        );
      } else {
        toast.error(r.error || t(locale, 'setup.toast.testFail'));
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  const steps = [
    { n: 1, title: t(locale, 'setup.step.welcome') },
    { n: 2, title: t(locale, 'setup.step.urls') },
    { n: 3, title: t(locale, 'setup.step.llm') },
    { n: 4, title: t(locale, 'setup.step.done') },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-10">
      <div className="flex flex-wrap items-center gap-3">
        <Rocket className="h-7 w-7 text-indigo-400" aria-hidden />
        <div>
          <h2 className="text-xl font-semibold text-white">{t(locale, 'setup.title')}</h2>
          <p className="text-sm text-gray-500">{t(locale, 'setup.subtitle')}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {steps.map((s) => (
          <button
            key={s.n}
            type="button"
            onClick={() => setStep(s.n)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              step === s.n
                ? 'bg-indigo-600 text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            {s.n}. {s.title}
          </button>
        ))}
      </div>

      {step === 1 && (
        <GlassCard className="p-6 space-y-4 border border-indigo-500/20">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-400" aria-hidden />
            {t(locale, 'setup.whatTitle')}
          </h3>
          <ul className="list-disc space-y-2 pl-5 text-sm text-gray-300 leading-relaxed">
            <li>{t(locale, 'setup.bullet.urls')}</li>
            <li>{t(locale, 'setup.bullet.llm')}</li>
            <li>{t(locale, 'setup.bullet.env')}</li>
            <li>{t(locale, 'setup.bullet.benchmark')}</li>
          </ul>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={() => setStep(2)}>
              {t(locale, 'setup.next')}
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
            <Button variant="secondary" onClick={() => router.replace('/admin?tab=dashboard')}>
              {t(locale, 'setup.skipDashboard')}
            </Button>
          </div>
        </GlassCard>
      )}

      {step === 2 && (
        <GlassCard className="p-6 space-y-4 border border-white/10">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <Link2 className="h-5 w-5 text-cyan-400" aria-hidden />
            {t(locale, 'setup.urlsTitle')}
          </h3>
          <p className="text-sm text-gray-300">
            {t(locale, 'setup.openedFrom')}{' '}
            <code className="rounded bg-black/40 px-2 py-0.5 text-indigo-200">{origin || '—'}</code>
          </p>
          <ul className="list-disc space-y-2 pl-5 text-sm text-gray-400 leading-relaxed">
            <li>{t(locale, 'setup.urls.li1')}</li>
            <li>{t(locale, 'setup.urls.li2')}</li>
            <li>{t(locale, 'setup.urls.li3')}</li>
          </ul>
          <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-3 text-xs leading-relaxed text-gray-400">
            <strong className="text-gray-200">{t(locale, 'setup.urls.benchmarkTitle')}</strong> —{' '}
            {t(locale, 'setup.urls.benchmarkBody')}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(1)}>
              {t(locale, 'setup.back')}
            </Button>
            <Button onClick={() => setStep(3)}>{t(locale, 'setup.nextLlm')}</Button>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-indigo-300 hover:underline px-3 py-2"
            >
              {t(locale, 'setup.openDocs')}
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          </div>
        </GlassCard>
      )}

      {step === 3 && (
        <GlassCard className="p-6 space-y-5 border border-emerald-500/15">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-emerald-400" aria-hidden />
            {t(locale, 'setup.llmTitle')}
          </h3>
          {!allowSave && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              {t(locale, 'setup.roleCannotModify')}
            </div>
          )}
          <p className="text-sm text-gray-400">{t(locale, 'setup.llmKeysPath')}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {(Object.keys(PRESETS) as PresetId[]).map((id) => {
              const p = PRESETS[id];
              const active = preset === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPreset(id)}
                  className={`rounded-xl border px-3 py-3 text-left text-sm transition-colors ${
                    active
                      ? 'border-indigo-500/60 bg-indigo-500/15 text-white'
                      : 'border-white/10 bg-white/[0.03] text-gray-300 hover:border-white/20'
                  }`}
                >
                  <div className="font-medium text-white">{p.label}</div>
                  <div className="mt-1 text-xs text-gray-500 leading-snug">{t(locale, PRESET_DESC_KEY[id])}</div>
                  {providerNames.has(p.name) ? (
                    <div className="mt-2 text-[10px] uppercase tracking-wide text-amber-400/90">
                      {t(locale, 'setup.preset.exists')}
                    </div>
                  ) : (
                    <div className="mt-2 text-[10px] uppercase tracking-wide text-gray-600">
                      {t(locale, 'setup.preset.create')}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">{t(locale, 'setup.apiKey')}</label>
            <Input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={t(locale, 'setup.apiKeyPlaceholder')}
              className="font-mono text-sm"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={makeDefault}
              onChange={(e) => setMakeDefault(e.target.checked)}
              className="rounded border-white/20 bg-white/5"
            />
            {t(locale, 'setup.makeDefault')}
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(2)}>
              {t(locale, 'setup.back')}
            </Button>
            <Button onClick={() => void saveProviderStep()} disabled={saving || !allowSave}>
              {saving ? t(locale, 'setup.saving') : t(locale, 'setup.saveProvider')}
            </Button>
            <Button variant="secondary" onClick={() => setStep(4)} disabled={saving}>
              {t(locale, 'setup.skipLater')}
            </Button>
          </div>
          <p className="text-xs text-gray-600">{t(locale, 'setup.providersOllama')}</p>
        </GlassCard>
      )}

      {step === 4 && (
        <GlassCard className="p-6 space-y-5 border border-indigo-500/20">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <PartyPopper className="h-5 w-5 text-amber-400" aria-hidden />
            {t(locale, 'setup.doneTitle')}
          </h3>
          <ul className="space-y-2 text-sm text-gray-300">
            <li className="flex gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" aria-hidden />
              {t(locale, 'setup.done.newProduct')}
            </li>
            <li className="flex gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" aria-hidden />
              {t(locale, 'setup.done.settings')}
            </li>
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(3)}>
              {t(locale, 'setup.back')}
            </Button>
            <Button onClick={() => void runQuickTest()} disabled={testing || !allowSave}>
              {testing
                ? t(locale, 'setup.testing')
                : tVars(locale, 'setup.testModel', { label: PRESETS[preset].label })}
            </Button>
            <Button onClick={() => router.replace('/admin?tab=new-product')}>
              {t(locale, 'setup.openNewProduct')}
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
            <Button variant="secondary" onClick={() => router.replace('/admin?tab=settings')}>
              {t(locale, 'setup.platformSettings')}
            </Button>
          </div>
          <div className="border-t border-white/10 pt-4 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={markComplete}
              className={markedDone ? 'border-emerald-500/40 text-emerald-200' : ''}
            >
              {markedDone ? t(locale, 'setup.markedComplete') : t(locale, 'setup.markComplete')}
            </Button>
            <span className="text-xs text-gray-500">{t(locale, 'setup.markHint')}</span>
          </div>
        </GlassCard>
      )}
    </div>
  );
}

export function isSetupWizardMarkedDone(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem(STORAGE_DONE) === '1';
  } catch {
    return false;
  }
}
