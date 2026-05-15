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

const STEPS = ['Idea', 'Options', 'Review'] as const;

const STEP_GUIDE = [
  {
    step: 1,
    name: 'Idea',
    headline: 'Describe the outcome',
    body: 'Focus on who it helps and what changes for them. Technical stack comes later.',
    checklist: ['Plain language', 'Optional AI assist (with consent)', 'Heuristic hints when patterns match'],
    eta: 'about 1 minute',
  },
  {
    step: 2,
    name: 'Options',
    headline: 'Shape how the factory runs',
    body: 'Delivery profile, prototype vs production, and instructions every agent reads.',
    checklist: ['Templates: this browser or cloud', 'Quick-start chips on the left', 'Save presets for repeat work'],
    eta: 'about 2 minutes',
  },
  {
    step: 3,
    name: 'Review',
    headline: 'Confirm and enqueue',
    body: 'We create a pipeline product and hand it to agents. You can still stop or rework from Pipeline.',
    checklist: ['Check lengths and modes', 'Retry with clearer instructions if create fails', 'Follow links to Providers if LLM errors appear'],
    eta: 'under a minute',
  },
] as const;

const QUICK_PRESETS = [
  {
    id: 'saas',
    label: 'B2B SaaS MVP',
    short: 'Full pipeline · prototype',
    idea:
      'B2B SaaS for small logistics brokers to quote spot freight in under five minutes: multi-tenant orgs, role-based access, quote builder with PDF export, email notifications, and a minimal Stripe-ready billing stub (no live keys).',
    deliveryChoice: 'full_software' as const,
    mode: 'prototype' as const,
    instructions:
      'TypeScript backend, React admin UI, Postgres. Include auth, org/workspace model, audit log for quote changes, and OpenAPI for core resources. Prioritize clarity over feature breadth.',
  },
  {
    id: 'landing',
    label: 'Marketing / waitlist landing',
    short: 'Landing profile · fast path',
    idea:
      'Single marketing landing page for a privacy-first analytics product: hero, social proof, feature grid, pricing teaser, FAQ, waitlist form with double opt-in copy, and strong CTA.',
    deliveryChoice: 'marketing_landing' as const,
    mode: 'prototype' as const,
    instructions:
      'Premium layout, responsive, accessible headings. Relative asset paths only. No backend beyond static form placeholder.',
  },
  {
    id: 'internal',
    label: 'Internal admin tool',
    short: 'Full product · production-minded',
    idea:
      'Internal web console for support staff to search customers, view recent pipeline runs, and attach internal notes (not customer-visible).',
    deliveryChoice: 'full_software' as const,
    mode: 'production' as const,
    instructions:
      'Hardened defaults: structured logging, no PII in client logs, conservative error messages. English UI.',
  },
] as const;

const INTRO_STORAGE = 'aicom_new_product_intro_dismissed_v1';

export function NewProductTab() {
  const [step, setStep] = useState(1);
  const [idea, setIdea] = useState('');
  const [instructions, setInstructions] = useState('');
  const [deliveryChoice, setDeliveryChoice] = useState<'full_software' | 'marketing_landing' | 'infer'>(
    'full_software',
  );
  const [mode, setMode] = useState<'prototype' | 'production'>('prototype');
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
    setMode(p.mode);
    setInstructions(p.instructions);
    setStep(2);
    toast.success(`Loaded preset: ${p.label} — review Options, then continue.`);
  };

  const applyTemplate = (t: ProductCreationTemplate) => {
    setDeliveryChoice(t.deliveryChoice);
    setMode(t.mode);
    setInstructions(t.instructions);
    toast.success(`Applied template “${t.name}”`);
  };

  const applyCloudTemplate = (t: (typeof cloudTemplates)[0]) => {
    const dp = t.delivery_profile;
    if (dp === 'marketing_landing' || dp === 'full_software' || dp === 'infer') {
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
      if (dp === 'marketing_landing' || dp === 'full_software' || dp === 'infer') {
        setDeliveryChoice(dp);
      }
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
        ...(deliveryChoice !== 'infer' ? { delivery_profile: deliveryChoice } : {}),
      });
      const pid = typeof data.product_id === 'string' ? data.product_id : null;
      setCreatedId(pid);
      setResult(pid ? `Product created successfully! ID: ${pid}` : 'Product created successfully!');
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
      toast.success(`${label} copied`);
    } catch {
      toast.error('Clipboard unavailable');
    }
  };

  const showHeuristic =
    hint.suggestedDelivery &&
    !dismissedHint &&
    deliveryChoice !== 'infer' &&
    hint.suggestedDelivery !== deliveryChoice;

  const guide = STEP_GUIDE[step - 1];

  return (
    <div className="mx-auto w-full max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <GlassCard>
          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles className="h-6 w-6 shrink-0 text-indigo-400" />
              <div>
                <h2 className="text-xl font-semibold text-white">Create New Product</h2>
                <p className="text-sm text-gray-400">
                  Guided wizard: idea → factory options → review. Templates are first-class — local, cloud, and
                  quick-start chips.
                </p>
              </div>
            </div>
          </div>

          <div className="mb-6 space-y-2">
            <div className="flex justify-between text-xs text-gray-500">
              <span>
                Step {step} of {STEPS.length} — {guide.name}
              </span>
              <span className="text-gray-600">{guide.eta}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full bg-indigo-500 transition-[width] duration-300"
                style={{ width: `${(step / STEPS.length) * 100}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {STEPS.map((label, i) => {
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
                  <p className="font-medium text-white">First time here?</p>
                  <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed">
                    <li>Use a quick-start chip (left on desktop, below on mobile) or write your own idea.</li>
                    <li>Cloud templates sync with your factory data directory — save once, reuse from any browser.</li>
                    <li>If creation fails, use the suggested links on the error card (Providers, Pipeline, retry).</li>
                  </ul>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg p-1 text-indigo-200 hover:bg-white/10"
                  aria-label="Dismiss intro"
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
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">This step</p>
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
                  Quick-start templates
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-emerald-100/80">
                  Fills idea + options so you edit instead of starting from a blank page. Sends you to Options when done.
                </p>
                <div className="mt-3 flex flex-col gap-2">
                  {QUICK_PRESETS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => applyQuickPreset(p)}
                      className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-left text-xs text-emerald-50 transition hover:bg-emerald-500/20"
                    >
                      <span className="block font-medium">{p.label}</span>
                      <span className="mt-0.5 block text-[10px] text-emerald-100/75">{p.short}</span>
                    </button>
                  ))}
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
                      Product idea <span className="text-red-400">*</span>
                    </label>
                    <textarea
                      className="input-glass min-h-[140px] resize-y"
                      placeholder="Describe the product you want to build..."
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
                            setDismissedHint(true);
                            toast.success('Delivery profile updated from suggestion');
                          }}
                        >
                          Apply: {hint.suggestedDelivery === 'marketing_landing' ? 'Marketing landing' : 'Full product'}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setDismissedHint(true)}>
                          Dismiss
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
                      <span>
                        Allow one lightweight LLM round-trip to suggest delivery profile, mode, and admin instructions.
                        Your idea is only sent when you press the button below.
                      </span>
                    </label>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={!idea.trim() || !consentAiPrefill || aiBusy}
                      onClick={() => void runAiPrefill()}
                    >
                      {aiBusy ? 'Calling model…' : 'Suggest with AI (opens Options step)'}
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
                      Next
                    </Button>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-5">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">Admin Instructions (optional)</label>
                    <textarea
                      className="input-glass min-h-[140px] resize-y"
                      placeholder="Stack, tone, compliance — passed to every agent."
                      value={instructions}
                      onChange={(e) => setInstructions(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">What to ship</label>
                    <select
                      value={deliveryChoice}
                      onChange={(e) =>
                        setDeliveryChoice(e.target.value as 'full_software' | 'marketing_landing' | 'infer')
                      }
                      className="input-glass"
                    >
                      <option value="full_software">Full product (app / service scope)</option>
                      <option value="marketing_landing">Marketing landing only</option>
                      <option value="infer">Auto-detect from idea (legacy)</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-300">Delivery mode</label>
                    <select
                      value={mode}
                      onChange={(e) => setMode(e.target.value as 'prototype' | 'production')}
                      className="input-glass"
                    >
                      <option value="prototype">prototype</option>
                      <option value="production">production</option>
                    </select>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-300">
                      <LayoutList className="h-4 w-4 text-cyan-400" />
                      Product templates (this browser)
                    </div>
                    <p className="mb-3 text-xs text-gray-500">
                      Save the current options row as a reusable recipe — stored only in localStorage on this device.
                    </p>
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
                      Back
                    </Button>
                    <Button type="button" onClick={() => setStep(3)} icon={<ChevronRight className="h-4 w-4" />}>
                      Next
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
                      <li>Instructions: {instructions.trim() ? `${instructions.trim().length} chars` : 'none'}</li>
                    </ul>
                  </div>
                  <div className="flex justify-between gap-2">
                    <Button type="button" variant="ghost" onClick={() => setStep(2)} icon={<ChevronLeft className="h-4 w-4" />}>
                      Back
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
