'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
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
import toast from 'react-hot-toast';

const STORAGE_DONE = 'aicom_admin_setup_wizard_done_v1';
/** Dispatched on `window` when the user marks the setup checklist complete (same tab). */
export const SETUP_WIZARD_DONE_EVENT = 'aicom-setup-wizard-done';

type PresetId = 'deepseek_api' | 'anthropic_cloud' | 'groq_api';

const PRESETS: Record<
  PresetId,
  Omit<CreateProviderPayload, 'api_key'> & { description: string; label: string }
> = {
  deepseek_api: {
    label: 'DeepSeek',
    description: 'OpenAI-compatible API — common default for this factory.',
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
    description: 'Claude API (native Anthropic provider type in the factory).',
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
    description: 'Fast OpenAI-compatible inference (Llama, Mixtral, …).',
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

export function SetupWizardTab({ adminRole }: { adminRole: string | null }) {
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
    toast.success('Setup checklist marked complete');
  };

  const saveProviderStep = async () => {
    if (!allowSave) {
      toast.error('Your role cannot change LLM providers — ask an admin.');
      return;
    }
    const base = PRESETS[preset];
    const key = apiKey.trim();
    if (!key) {
      toast.error('Paste an API key, or skip this step and configure providers later.');
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
        toast.success(`Updated ${base.label} and stored the key in model_providers.yaml`);
      } else {
        await api.createProvider(payload);
        toast.success(`Added ${base.label} and stored the key in model_providers.yaml`);
      }
      if (makeDefault) {
        await api.setDefaultProvider(base.name);
        toast.success(`Default provider set to ${base.name}`);
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
        toast.success(`Test OK (${r.latency_ms} ms, model ${r.model || '—'})`);
      } else {
        toast.error(r.error || 'Test failed');
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  const steps = [
    { n: 1, title: 'Welcome' },
    { n: 2, title: 'URLs & deploy' },
    { n: 3, title: 'LLM key' },
    { n: 4, title: 'Done' },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-10">
      <div className="flex flex-wrap items-center gap-3">
        <Rocket className="h-7 w-7 text-indigo-400" aria-hidden />
        <div>
          <h2 className="text-xl font-semibold text-white">Setup wizard</h2>
          <p className="text-sm text-gray-500">
 Guided first-time wiring — advanced operators still use <code className="text-gray-400">.env</code> and{' '}
            <Link href="/docs" className="text-indigo-300 hover:underline">
              /docs
            </Link>
            .
          </p>
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
            What this wizard does
          </h3>
          <ul className="list-disc space-y-2 pl-5 text-sm text-gray-300 leading-relaxed">
            <li>
              <strong className="text-white">URLs</strong> — confirm how the browser reaches the app (and when you
              must set build-time <code className="text-gray-400">NEXT_PUBLIC_SITE_URL</code>).
            </li>
            <li>
              <strong className="text-white">LLM</strong> — paste one API key; we save it to{' '}
              <code className="text-gray-400">data/config/model_providers.yaml</code> on the server (same as{' '}
              <strong className="text-white">Providers</strong> tab). Optional: set as default router target.
            </li>
            <li>
              <strong className="text-white">.env</strong> — still supported for CI/CD, Compose secrets, and keys you
              do not want in YAML. This wizard does not replace it — it just avoids mandatory manual editing for the
              common path.
            </li>
            <li>
              <strong className="text-white">Director SLO benchmark</strong> (optional ops): autonomous benchmark runs
              need an admin JWT in the environment — see step 2. Without it, the factory skips them so the API is not
              hit with unauthenticated calls.
            </li>
          </ul>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={() => setStep(2)}>
              Next
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
            <Button variant="secondary" onClick={() => router.replace('/admin?tab=dashboard')}>
              Skip to dashboard
            </Button>
          </div>
        </GlassCard>
      )}

      {step === 2 && (
        <GlassCard className="p-6 space-y-4 border border-white/10">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <Link2 className="h-5 w-5 text-cyan-400" aria-hidden />
            Public URL &amp; build-time site URL
          </h3>
          <p className="text-sm text-gray-300">
            You opened Admin from:{' '}
            <code className="rounded bg-black/40 px-2 py-0.5 text-indigo-200">{origin || '—'}</code>
          </p>
          <ul className="list-disc space-y-2 pl-5 text-sm text-gray-400 leading-relaxed">
            <li>
              Storefront and admin links baked at <strong className="text-gray-200">Next.js build</strong> use{' '}
              <code className="text-gray-500">NEXT_PUBLIC_SITE_URL</code>. For Docker, set it in{' '}
              <code className="text-gray-500">.env</code> / Compose <strong className="text-gray-200">before</strong>{' '}
              <code className="text-gray-500">docker compose build</code> if the public URL is not localhost.
            </li>
            <li>
              The API tab in Compose maps host ports to <code className="text-gray-500">8080/8081</code> inside the
              container; the bundled UI talks to the API via loopback — no extra step for the default layout.
            </li>
            <li>
              Custom domains: set <code className="text-gray-500">AIFACTORY_CORS_ORIGINS</code> (see configuration docs).
            </li>
          </ul>
          <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-3 text-xs leading-relaxed text-gray-400">
            <strong className="text-gray-200">Director / SLO benchmark (optional, production)</strong> — when pipeline SLO
            is breached, the Director can spawn <code className="text-gray-500">benchmark_pass_rate.py</code>, which
            calls <strong className="text-gray-300">admin</strong> HTTP APIs. The script exits early unless a JWT is
            configured: set <code className="text-gray-500">AIFACTORY_BENCHMARK_ADMIN_TOKEN</code> or{' '}
            <code className="text-gray-500">AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE</code> (e.g. a one-line file under{' '}
            <code className="text-gray-500">data/secrets/</code> on the host volume, <code className="text-gray-500">chmod 600</code>
            ). Full steps live in the repo file <code className="text-gray-500">docs/configuration.md</code> (section{' '}
            <span className="text-gray-300">Director / benchmark league</span>). Without these variables, benchmarks are
            skipped by design — not an error.
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button onClick={() => setStep(3)}>Next: LLM key</Button>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-indigo-300 hover:underline px-3 py-2"
            >
              Open /docs
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          </div>
        </GlassCard>
      )}

      {step === 3 && (
        <GlassCard className="p-6 space-y-5 border border-emerald-500/15">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-emerald-400" aria-hidden />
            Add one LLM provider
          </h3>
          {!allowSave && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              Your account role cannot modify providers. Open the read-only{' '}
              <Link href="/admin?tab=providers" className="underline">
                Providers
              </Link>{' '}
              tab or ask an <strong>admin</strong> to run this step.
            </div>
          )}
          <p className="text-sm text-gray-400">
            Keys are written to the server&apos;s <code className="text-gray-500">model_providers.yaml</code> (under
            the persisted <code className="text-gray-500">data/</code> directory in Docker). For production, prefer
            env-based keys if your policy requires it — configure that in the full Providers UI.
          </p>
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
                  <div className="mt-1 text-xs text-gray-500 leading-snug">{p.description}</div>
                  {providerNames.has(p.name) ? (
                    <div className="mt-2 text-[10px] uppercase tracking-wide text-amber-400/90">Already exists — will update</div>
                  ) : (
                    <div className="mt-2 text-[10px] uppercase tracking-wide text-gray-600">Will create</div>
                  )}
                </button>
              );
            })}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">API key</label>
            <Input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Paste key — stored on server when you save"
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
            Set this provider as the default (<code className="text-gray-500">default_provider</code>)
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(2)}>
              Back
            </Button>
            <Button onClick={() => void saveProviderStep()} disabled={saving || !allowSave}>
              {saving ? 'Saving…' : 'Save provider'}
            </Button>
            <Button variant="secondary" onClick={() => setStep(4)} disabled={saving}>
              Skip (configure later)
            </Button>
          </div>
          <p className="text-xs text-gray-600">
            Need Ollama, Together, or custom endpoints? Use{' '}
            <Link href="/admin?tab=providers" className="text-indigo-400 hover:underline">
              Providers → Add
            </Link>
            .
          </p>
        </GlassCard>
      )}

      {step === 4 && (
        <GlassCard className="p-6 space-y-5 border border-indigo-500/20">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <PartyPopper className="h-5 w-5 text-amber-400" aria-hidden />
            You&apos;re ready to run the factory
          </h3>
          <ul className="space-y-2 text-sm text-gray-300">
            <li className="flex gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" aria-hidden />
              Queue a product from <strong className="text-white">New product</strong> (guided wizard there too).
            </li>
            <li className="flex gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" aria-hidden />
              Tune automation under <strong className="text-white">Settings</strong> and <strong className="text-white">Director</strong>.
            </li>
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setStep(3)}>
              Back
            </Button>
            <Button onClick={() => void runQuickTest()} disabled={testing || !allowSave}>
              {testing ? 'Testing…' : `Test ${PRESETS[preset].label} (light model)`}
            </Button>
            <Button onClick={() => router.replace('/admin?tab=new-product')}>
              Open New product
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden />
            </Button>
            <Button variant="secondary" onClick={() => router.replace('/admin?tab=settings')}>
              Platform settings
            </Button>
          </div>
          <div className="border-t border-white/10 pt-4 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={markComplete}
              className={markedDone ? 'border-emerald-500/40 text-emerald-200' : ''}
            >
              {markedDone ? 'Marked complete ✓' : 'Mark setup checklist complete'}
            </Button>
            <span className="text-xs text-gray-500">
              Hides the gentle reminder in the onboarding strip (local browser only).
            </span>
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
