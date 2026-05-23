'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Sparkles,
  Send,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Save,
  Trash2,
  Copy,
  ExternalLink,
  Lightbulb,
  LayoutList,
  BookOpen,
  ListChecks,
  Zap,
  X,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ActionableFailurePanel } from '@/components/ui/ActionableFailurePanel';
import { inferProductDefaultsFromIdea } from '@/lib/inferProductDefaultsFromIdea';
import { resolveActionableFailure } from '@/lib/actionableErrors';
import {
  deleteProductCreationTemplate,
  listProductCreationTemplates,
  upsertProductCreationTemplate,
  type ProductCreationTemplate,
} from '@/lib/productCreationTemplates';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import {
  CONTENT_LOCALE_OPTIONS,
  contentLocaleLabel,
  type ContentLocaleChoice,
} from '@/lib/contentLanguages';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

function getStepLabels(locale: AdminLocale): readonly [string, string, string] {
  return [
    t(locale, 'newProduct.step.idea'),
    t(locale, 'newProduct.step.options'),
    t(locale, 'newProduct.step.review'),
  ];
}

function getStepGuide(locale: AdminLocale) {
  return [
    {
      step: 1,
      name: t(locale, 'newProduct.step.idea'),
      headline: t(locale, 'newProduct.guide1.headline'),
      body: t(locale, 'newProduct.guide1.body'),
      checklist: [
        t(locale, 'newProduct.guide1.c1'),
        t(locale, 'newProduct.guide1.c2'),
        t(locale, 'newProduct.guide1.c3'),
      ],
      eta: t(locale, 'newProduct.guide1.eta'),
    },
    {
      step: 2,
      name: t(locale, 'newProduct.step.options'),
      headline: t(locale, 'newProduct.guide2.headline'),
      body: t(locale, 'newProduct.guide2.body'),
      checklist: [
        t(locale, 'newProduct.guide2.c1'),
        t(locale, 'newProduct.guide2.c2'),
        t(locale, 'newProduct.guide2.c3'),
      ],
      eta: t(locale, 'newProduct.guide2.eta'),
    },
    {
      step: 3,
      name: t(locale, 'newProduct.step.review'),
      headline: t(locale, 'newProduct.guide3.headline'),
      body: t(locale, 'newProduct.guide3.body'),
      checklist: [
        t(locale, 'newProduct.guide3.c1'),
        t(locale, 'newProduct.guide3.c2'),
        t(locale, 'newProduct.guide3.c3'),
      ],
      eta: t(locale, 'newProduct.guide3.eta'),
    },
  ] as const;
}

const QUICK_PRESET_I18N: Record<
  string,
  { labelKey: string; shortKey: string }
> = {
  saas: { labelKey: 'newProduct.preset.b2b.label', shortKey: 'newProduct.preset.b2b.short' },
  landing: { labelKey: 'newProduct.preset.landing.label', shortKey: 'newProduct.preset.landing.short' },
  internal: { labelKey: 'newProduct.preset.internal.label', shortKey: 'newProduct.preset.internal.short' },
  desktop: { labelKey: 'newProduct.preset.desktop.label', shortKey: 'newProduct.preset.desktop.short' },
};

const QUICK_PRESETS = [
  {
    id: 'desktop',
    idea:
      'Tauri desktop app for local-first contract review: drag-drop PDF/DOCX, offline clause highlighting, jurisdiction rule packs, optional AI Market capability hooks. macOS / Windows / Linux.',
    deliveryChoice: 'desktop_app' as const,
    mode: 'prototype' as const,
    instructions:
      'Tauri v2 + Rust backend commands. WebView UI in ui/. Local SQLite for session state. No cloud upload of document text. README with cargo tauri dev/build.',
  },
  {
    id: 'saas',
    idea:
      'B2B SaaS for small logistics brokers to quote spot freight in under five minutes: multi-tenant orgs, role-based access, quote builder with PDF export, email notifications, and a minimal Stripe-ready billing stub (no live keys).',
    deliveryChoice: 'full_software' as const,
    mode: 'prototype' as const,
    instructions:
      'TypeScript backend, React admin UI, Postgres. Include auth, org/workspace model, audit log for quote changes, and OpenAPI for core resources. Prioritize clarity over feature breadth.',
  },
  {
    id: 'landing',
    idea:
      'Single marketing landing page for a privacy-first analytics product: hero, social proof, feature grid, pricing teaser, FAQ, waitlist form with double opt-in copy, and strong CTA.',
    deliveryChoice: 'marketing_landing' as const,
    mode: 'prototype' as const,
    instructions:
      'Premium layout, responsive, accessible headings. Relative asset paths only. No backend beyond static form placeholder.',
  },
  {
    id: 'internal',
    idea:
      'Internal web console for support staff to search customers, view recent pipeline runs, and attach internal notes (not customer-visible).',
    deliveryChoice: 'full_software' as const,
    mode: 'production' as const,
    instructions:
      'Hardened defaults: structured logging, no PII in client logs, conservative error messages. English UI.',
  },
] as const;

const INTRO_STORAGE = 'aicom_new_product_intro_dismissed_v1';

export function NewProductTab({ locale }: { locale: AdminLocale }) {
  const stepLabels = useMemo(() => getStepLabels(locale), [locale]);
  const [step, setStep] = useState(1);
  const [idea, setIdea] = useState('');
  const [instructions, setInstructions] = useState('');
  const [deliveryChoice, setDeliveryChoice] = useState<
    'full_software' | 'marketing_landing' | 'desktop_app' | 'infer'
  >('full_software');
  const [categoryChoice, setCategoryChoice] = useState<string>('saas');
  const [mode, setMode] = useState<'prototype' | 'production'>('prototype');
  const [contentLocale, setContentLocale] = useState<ContentLocaleChoice>('auto');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [submitFailure, setSubmitFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [templatesFailure, setTemplatesFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [prefillFailure, setPrefillFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [cloudOpFailure, setCloudOpFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [templates, setTemplates] = useState<ProductCreationTemplate[]>([]);
  const [cloudTemplates, setCloudTemplates] = useState<
    { id: string; name: string; delivery_profile: string; production_mode: boolean; instructions: string }[]
  >([]);
  const [templateName, setTemplateName] = useState('');
  const [dismissedHint, setDismissedHint] = useState(false);
  const [consentAiPrefill, setConsentAiPrefill] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [introDismissed, setIntroDismissed] = useState(true);

  const hint = useMemo(() => inferProductDefaultsFromIdea(idea), [idea]);

  useEffect(() => {
    try {
      setIntroDismissed(localStorage.getItem(INTRO_STORAGE) === '1');
    } catch {
      setIntroDismissed(false);
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('idea');
    if (fromUrl) {
      setIdea(decodeURIComponent(fromUrl.replace(/\+/g, ' ')));
      return;
    }
    try {
      const stored = sessionStorage.getItem('aicom_prefill_idea');
      if (stored) {
        setIdea(stored);
        sessionStorage.removeItem('aicom_prefill_idea');
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    setTemplates(listProductCreationTemplates());
  }, []);

  const loadCloudTemplates = useCallback(async () => {
    setTemplatesFailure(null);
    try {
      const res = await api.listIterationUserTemplates();
      setCloudTemplates(
        (res.templates || []).map((t: Record<string, unknown>) => ({
          id: String(t.id || ''),
          name: String(t.name || ''),
          delivery_profile: String(t.delivery_profile || 'infer'),
          production_mode: Boolean(t.production_mode),
          instructions: String(t.instructions || ''),
        })),
      );
    } catch (e: unknown) {
      setTemplatesFailure(resolveActionableFailure(e, { operation: 'iteration_templates' }));
      setCloudTemplates([]);
    }
  }, []);

  useEffect(() => {
    void loadCloudTemplates();
  }, [loadCloudTemplates]);

  useEffect(() => {
    setDismissedHint(false);
  }, [idea]);

  const dismissIntro = () => {
    try {
      localStorage.setItem(INTRO_STORAGE, '1');
    } catch {
      /* ignore */
    }
    setIntroDismissed(true);
  };

  const applyQuickPreset = (p: (typeof QUICK_PRESETS)[number]) => {
    setIdea(p.idea);
    setDeliveryChoice(p.deliveryChoice);
    setCategoryChoice(p.id === 'desktop' ? 'desktop' : p.id === 'landing' ? 'landings' : 'saas');
    setMode(p.mode);
    setInstructions(p.instructions);
    setStep(2);
    toast.success(
      `${t(locale, QUICK_PRESET_I18N[p.id].labelKey)} — ${t(locale, 'newProduct.step.options')}`,
    );
  };

  const applyTemplate = (t: ProductCreationTemplate) => {
    setDeliveryChoice(t.deliveryChoice);
    setMode(t.mode);
    setInstructions(t.instructions);
    toast.success(`Applied template “${t.name}”`);
  };

  const applyCloudTemplate = (t: (typeof cloudTemplates)[0]) => {
    const dp = t.delivery_profile;
    if (dp === 'marketing_landing' || dp === 'full_software' || dp === 'desktop_app' || dp === 'infer') {
      setDeliveryChoice(dp);
    } else {
      setDeliveryChoice('infer');
    }
    setMode(t.production_mode ? 'production' : 'prototype');
    setInstructions(t.instructions);
    toast.success(`Applied cloud template “${t.name}”`);
  };

  const saveCurrentAsCloudTemplate = async () => {
    const name = templateName.trim() || `Cloud ${new Date().toLocaleString()}`;
    setCloudOpFailure(null);
    try {
      await api.upsertIterationUserTemplate({
        name,
        delivery_profile: deliveryChoice,
        production_mode: mode === 'production',
        instructions,
      });
      setTemplateName('');
      await loadCloudTemplates();
      toast.success(`Saved to cloud: “${name}”`);
    } catch (e: unknown) {
      setCloudOpFailure(resolveActionableFailure(e, { operation: 'iteration_templates_write' }));
    }
  };

  const deleteCloudTemplate = async (id: string) => {
    setCloudOpFailure(null);
    try {
      await api.deleteIterationUserTemplate(id);
      setCloudTemplates((prev) => prev.filter((t) => t.id !== id));
      toast.success('Cloud template removed');
    } catch (e: unknown) {
      setCloudOpFailure(resolveActionableFailure(e, { operation: 'iteration_templates_delete' }));
    }
  };

  const runAiPrefill = async () => {
    if (!idea.trim() || !consentAiPrefill) return;
    setAiBusy(true);
    setPrefillFailure(null);
    try {
      const r = await api.prefillProductFromIdea({ idea: idea.trim(), consent: true });
      const dp = r.delivery_profile;
      if (dp === 'marketing_landing' || dp === 'full_software' || dp === 'desktop_app' || dp === 'infer') {
        setDeliveryChoice(dp);
      }
      if (dp === 'desktop_app') setCategoryChoice('desktop');
      setMode(r.production_mode ? 'production' : 'prototype');
      if (r.instructions) setInstructions(r.instructions);
      toast.success(`AI suggestion applied (${r.source})${r.rationale ? ` — ${r.rationale}` : ''}`);
      setStep(2);
    } catch (e: unknown) {
      setPrefillFailure(resolveActionableFailure(e, { operation: 'prefill_llm' }));
    } finally {
      setAiBusy(false);
    }
  };

  const saveCurrentAsTemplate = () => {
    const name = templateName.trim() || `Template ${new Date().toLocaleString()}`;
    upsertProductCreationTemplate({
      name,
      deliveryChoice,
      mode,
      instructions,
    });
    setTemplateName('');
    setTemplates(listProductCreationTemplates());
    toast.success(`Saved “${name}”`);
  };

  const handleSubmit = async () => {
    if (!idea.trim()) return;

    setSubmitting(true);
    setResult(null);
    setCreatedId(null);
    setSubmitFailure(null);

    try {
      const data = await api.createAdminProduct({
        idea: idea.trim(),
        admin_instructions: instructions.trim() || undefined,
        production_mode: mode === 'production',
        interface_locale: locale,
        content_locale: contentLocale,
        ...(deliveryChoice !== 'infer' ? { delivery_profile: deliveryChoice } : {}),
        ...(categoryChoice ? { category: categoryChoice } : {}),
      });
      const pid = typeof data.product_id === 'string' ? data.product_id : null;
      setCreatedId(pid);
      setResult(
        pid
          ? tVars(locale, 'newProduct.createdWithId', { id: pid })
          : t(locale, 'newProduct.created'),
      );
      setIdea('');
      setInstructions('');
      setStep(1);
    } catch (err: unknown) {
      setSubmitFailure(resolveActionableFailure(err, { operation: 'create_product' }));
    } finally {
      setSubmitting(false);
    }
  };

  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const storefrontUrl = createdId ? `${origin}/product/${encodeURIComponent(createdId)}` : '';
  const adminPipelineUrl = createdId ? `${origin}/admin?tab=pipeline&pipelineSearch=${encodeURIComponent(createdId)}` : '';

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(tVars(locale, 'common.copied', { label }));
    } catch {
      toast.error(t(locale, 'common.clipboardUnavailable'));
    }
  };

  const showHeuristic =
    hint.suggestedDelivery &&
    !dismissedHint &&
    deliveryChoice !== 'infer' &&
    hint.suggestedDelivery !== deliveryChoice;

  const guide = getStepGuide(locale)[step - 1];

  return (
    <div className="mx-auto w-full max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <GlassCard>
          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles className="h-6 w-6 shrink-0 text-indigo-400" />
              <div>
                <h2 className="text-xl font-semibold text-white">{t(locale, 'newProduct.title')}</h2>
                <p className="text-sm text-gray-400">{t(locale, 'newProduct.subtitle')}</p>
              </div>
            </div>
          </div>

          <div className="mb-6 space-y-2">
            <div className="flex justify-between text-xs text-gray-500">
              <span>
                {tVars(locale, 'newProduct.stepOf', {
                  step,
                  total: stepLabels.length,
                  name: guide.name,
                })}
              </span>
              <span className="text-gray-600">{guide.eta}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full bg-indigo-500 transition-[width] duration-300"
                style={{ width: `${(step / stepLabels.length) * 100}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {stepLabels.map((label, i) => {
                const n = i + 1;
                const active = step === n;
                return (
                  <button
                    key={label}
                    type="button"
                    onClick={() => setStep(n)}
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                      active ? 'bg-indigo-500 text-white' : 'bg-white/5 text-gray-500 hover:bg-white/10'
                    }`}
                  >
                    {n}. {label}
                  </button>
                );
              })}
            </div>
          </div>

          {!introDismissed ? (
            <div className="mb-6 rounded-xl border border-indigo-500/25 bg-indigo-950/30 p-4">
              <div className="flex gap-3">
                <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" aria-hidden />
                <div className="min-w-0 flex-1 space-y-2 text-sm text-indigo-100/90">
                  <p className="font-medium text-white">{t(locale, 'newProduct.intro.title')}</p>
                  <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed">
                    <li>{t(locale, 'newProduct.intro.li1')}</li>
                    <li>{t(locale, 'newProduct.intro.li2')}</li>
                    <li>{t(locale, 'newProduct.intro.li3')}</li>
                  </ul>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg p-1 text-indigo-200 hover:bg-white/10"
                  aria-label={t(locale, 'newProduct.intro.dismiss')}
                  onClick={dismissIntro}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : null}

          <div className="grid gap-6 lg:grid-cols-[minmax(240px,280px)_1fr]">
            <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                  {t(locale, 'newProduct.thisStep')}
                </p>
                <p className="mt-2 text-sm font-medium text-white">{guide.headline}</p>
                <p className="mt-1 text-xs leading-relaxed text-gray-400">{guide.body}</p>
                <div className="mt-3 flex items-start gap-2 text-xs text-gray-400">
                  <ListChecks className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-500" aria-hidden />
                  <ul className="list-inside list-disc space-y-0.5">
                    {guide.checklist.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="rounded-xl border border-emerald-500/25 bg-emerald-950/25 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-emerald-200/90">
                  <Zap className="h-3.5 w-3.5" aria-hidden />
                  {t(locale, 'newProduct.quickStart')}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-emerald-100/80">
                  {t(locale, 'newProduct.quickStartHint')}
                </p>
                <div className="mt-3 flex flex-col gap-2">
                  {QUICK_PRESETS.map((p) => {
                    const i18n = QUICK_PRESET_I18N[p.id];
                    return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => applyQuickPreset(p)}
                      className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-left text-xs text-emerald-50 transition hover:bg-emerald-500/20"
                    >
                      <span className="block font-medium">{t(locale, i18n.labelKey)}</span>
                      <span className="mt-0.5 block text-[10px] text-emerald-100/75">{t(locale, i18n.shortKey)}</span>
                    </button>
                  );
                  })}
                </div>
              </div>

              {templatesFailure ? (
                <ActionableFailurePanel failure={templatesFailure} onRetry={() => void loadCloudTemplates()} />
              ) : null}
            </aside>

            <div className="min-w-0 space-y-6">
              {step === 1 && (
                <div className="space-y-4">
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-300">
                      <Lightbulb className="h-4 w-4 text-amber-400" />
                      {t(locale, 'newProduct.ideaLabel')} <span className="text-red-400">*</span>
                    </label>
                    <textarea
                      className="input-glass min-h-[140px] resize-y"
                      placeholder={t(locale, 'newProduct.ideaPlaceholder')}
                      value={idea}
                      onChange={(e) => setIdea(e.target.value)}
                    />
                  </div>
                  {showHeuristic ? (
                    <div className="flex flex-col gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-50/95">
                      <p>{hint.reason}</p>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setDeliveryChoice(hint.suggestedDelivery!);
                            if (hint.suggestedCategory) setCategoryChoice(hint.suggestedCategory);
                            setDismissedHint(true);
                            toast.success(t(locale, 'newProduct.suggestionApplied'));
                          }}
                        >
                          {tVars(locale, 'newProduct.applySuggestion', {
                            label:
                              hint.suggestedDelivery === 'marketing_landing'
                                ? t(locale, 'newProduct.applyLanding')
                                : hint.suggestedDelivery === 'desktop_app'
                                  ? t(locale, 'newProduct.delivery.desktop')
                                  : t(locale, 'newProduct.applyFull'),
                          })}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setDismissedHint(true)}>
                          {t(locale, 'common.dismiss')}
                        </Button>
                      </div>
                    </div>
                  ) : null}
                  <div className="space-y-2 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-3">
                    <label className="flex cursor-pointer items-start gap-2 text-xs text-gray-300">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={consentAiPrefill}
                        onChange={(e) => setConsentAiPrefill(e.target.checked)}
                      />
                      <span>{t(locale, 'newProduct.aiConsent')}</span>
                    </label>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={!idea.trim() || !consentAiPrefill || aiBusy}
                      onClick={() => void runAiPrefill()}
                    >
                      {aiBusy ? t(locale, 'newProduct.aiBusy') : t(locale, 'newProduct.aiSuggest')}
                    </Button>
                  </div>
                  {prefillFailure ? (
                    <ActionableFailurePanel
                      failure={prefillFailure}
                      onRetry={() => void runAiPrefill()}
                      retryLabel="Retry AI suggestion"
                    />
                  ) : null}
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      onClick={() => setStep(2)}
                      disabled={!idea.trim()}
                      icon={<ChevronRight className="h-4 w-4" />}
                    >
                      {t(locale, 'common.next')}
                    </Button>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-5">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">
                      {t(locale, 'newProduct.instructionsLabel')}
                    </label>
                    <textarea
                      className="input-glass min-h-[140px] resize-y"
                      placeholder={t(locale, 'newProduct.instructionsPlaceholder')}
                      value={instructions}
                      onChange={(e) => setInstructions(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">
                      {t(locale, 'newProduct.whatToShip')}
                    </label>
                    <select
                      value={deliveryChoice}
                      onChange={(e) =>
                        setDeliveryChoice(
                          e.target.value as 'full_software' | 'marketing_landing' | 'desktop_app' | 'infer',
                        )
                      }
                      className="input-glass"
                    >
                      <option value="full_software">{t(locale, 'newProduct.delivery.full')}</option>
                      <option value="desktop_app">{t(locale, 'newProduct.delivery.desktop')}</option>
                      <option value="marketing_landing">{t(locale, 'newProduct.delivery.landing')}</option>
                      <option value="infer">{t(locale, 'newProduct.delivery.infer')}</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">
                      {t(locale, 'newProduct.deliveryMode')}
                    </label>
                    <select
                      value={mode}
                      onChange={(e) => setMode(e.target.value as 'prototype' | 'production')}
                      className="input-glass"
                    >
                      <option value="prototype">{t(locale, 'newProduct.mode.prototype')}</option>
                      <option value="production">{t(locale, 'newProduct.mode.production')}</option>
                    </select>
                  </div>

                  <div className="rounded-xl border border-violet-500/25 bg-violet-500/5 p-3 space-y-2">
                    <label className="block text-sm font-medium text-gray-300">
                      {t(locale, 'newProduct.contentLanguage')}
                    </label>
                    <p className="text-xs text-gray-500 leading-relaxed">{t(locale, 'newProduct.contentLanguageHint')}</p>
                    <select
                      value={contentLocale}
                      onChange={(e) => setContentLocale(e.target.value as ContentLocaleChoice)}
                      className="input-glass"
                    >
                      {CONTENT_LOCALE_OPTIONS.map((opt) => (
                        <option key={opt.code} value={opt.code}>
                          {contentLocaleLabel(opt.code, locale)}
                          {opt.reach ? ` · ${opt.reach}` : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-300">
                      <LayoutList className="h-4 w-4 text-cyan-400" />
                      {t(locale, 'newProduct.templatesLocal')}
                    </div>
                    <p className="mb-3 text-xs text-gray-500">{t(locale, 'newProduct.templatesLocalHint')}</p>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <Input
                        value={templateName}
                        onChange={(e) => setTemplateName(e.target.value)}
                        placeholder="Template name"
                        className="sm:flex-1"
                      />
                      <Button type="button" variant="secondary" size="sm" onClick={saveCurrentAsTemplate} icon={<Save className="h-4 w-4" />}>
                        Save template
                      </Button>
                    </div>
                    {templates.length > 0 ? (
                      <ul className="mt-3 space-y-1.5 text-sm">
                        {templates.map((t) => (
                          <li
                            key={t.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/5 bg-black/20 px-2 py-1.5"
                          >
                            <span className="text-gray-200">{t.name}</span>
                            <span className="flex gap-1">
                              <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => applyTemplate(t)}>
                                Apply
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs text-red-300 hover:text-red-200"
                                onClick={() => {
                                  deleteProductCreationTemplate(t.id);
                                  setTemplates(listProductCreationTemplates());
                                }}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-xs text-gray-600">No local templates yet — save one above, or use a quick-start chip.</p>
                    )}
                  </div>

                  <div className="rounded-xl border border-cyan-500/25 bg-cyan-500/5 p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-300">
                      <LayoutList className="h-4 w-4 text-cyan-300" />
                      Cloud templates (factory data dir)
                    </div>
                    <p className="mb-3 text-xs text-gray-500">
                      Synced across browsers that share this factory storage. Requires admin API access.
                    </p>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <Button type="button" variant="secondary" size="sm" onClick={() => void saveCurrentAsCloudTemplate()}>
                        Save current to cloud
                      </Button>
                    </div>
                    {cloudOpFailure ? (
                      <div className="mt-3">
                        <ActionableFailurePanel failure={cloudOpFailure} onRetry={() => void saveCurrentAsCloudTemplate()} />
                      </div>
                    ) : null}
                    {cloudTemplates.length > 0 ? (
                      <ul className="mt-3 space-y-1.5 text-sm">
                        {cloudTemplates.map((t) => (
                          <li
                            key={t.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/5 bg-black/20 px-2 py-1.5"
                          >
                            <span className="text-gray-200">{t.name}</span>
                            <span className="flex gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => applyCloudTemplate(t)}
                              >
                                Apply
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs text-red-300 hover:text-red-200"
                                onClick={() => void deleteCloudTemplate(t.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-xs text-gray-600">
                        {templatesFailure
                          ? 'Cloud list could not load — use retry on the left.'
                          : 'No cloud templates yet — save the current row to cloud, or fix API access if you expected some.'}
                      </p>
                    )}
                  </div>

                  <div className="flex justify-between">
                    <Button type="button" variant="ghost" onClick={() => setStep(1)} icon={<ChevronLeft className="h-4 w-4" />}>
                      {t(locale, 'common.back')}
                    </Button>
                    <Button type="button" onClick={() => setStep(3)} icon={<ChevronRight className="h-4 w-4" />}>
                      {t(locale, 'common.next')}
                    </Button>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4">
                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-300">
                    <p className="mb-2 font-medium text-white">Review</p>
                    <ul className="list-inside list-disc space-y-1 text-gray-400">
                      <li>Idea length: {idea.trim().length} chars</li>
                      <li>Delivery: {deliveryChoice}</li>
                      <li>Mode: {mode}</li>
                      <li>
                        {t(locale, 'newProduct.contentLanguage')}: {contentLocaleLabel(contentLocale, locale)}
                      </li>
                      <li>UI locale: {locale}</li>
                      <li>Instructions: {instructions.trim() ? `${instructions.trim().length} chars` : 'none'}</li>
                    </ul>
                  </div>
                  <div className="flex justify-between gap-2">
                    <Button type="button" variant="ghost" onClick={() => setStep(2)} icon={<ChevronLeft className="h-4 w-4" />}>
                      {t(locale, 'common.back')}
                    </Button>
                    <Button
                      onClick={() => void handleSubmit()}
                      loading={submitting}
                      disabled={!idea.trim()}
                      icon={<Send className="h-4 w-4" />}
                    >
                      Start building
                    </Button>
                  </div>
                </div>
              )}

              {result && (
                <div className="glass rounded-xl border border-emerald-500/30 p-4">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
                    <div className="min-w-0 flex-1 space-y-3">
                      <p className="text-sm text-emerald-300">{result}</p>
                      {createdId ? (
                        <div className="flex flex-col gap-2 text-xs">
                          <p className="text-gray-500">Share &amp; monitor</p>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              className="text-xs"
                              onClick={() => void copyText('Storefront URL', storefrontUrl)}
                            >
                              <Copy className="mr-1 h-3.5 w-3.5" />
                              Copy public product URL
                            </Button>
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              className="text-xs"
                              onClick={() => void copyText('Admin pipeline URL', adminPipelineUrl)}
                            >
                              <Copy className="mr-1 h-3.5 w-3.5" />
                              Copy admin pipeline link
                            </Button>
                            <a
                              href={storefrontUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 rounded-md border border-white/15 px-2 py-1 text-indigo-200 hover:bg-white/5"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                              Open storefront
                            </a>
                          </div>
                          <p className="break-all font-mono text-[10px] text-gray-600">{storefrontUrl}</p>
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">Monitor progress in the Pipeline tab.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {submitFailure ? (
                <ActionableFailurePanel failure={submitFailure} onRetry={() => void handleSubmit()} retryLabel="Retry create product" />
              ) : null}
            </div>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  );
}
