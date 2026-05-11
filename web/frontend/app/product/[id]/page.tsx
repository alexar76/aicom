'use client';

import React, { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Bot,
  Code2,
  FileText,
  Shield,
  ShoppingCart,
  BarChart3,
  ExternalLink,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Tag,
  DollarSign,
  Zap,
  Loader2,
  Layers,
  Server,
  Database,
  Package,
  Share2,
  Users,
  Megaphone,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import api, { Product } from '@/lib/api';
import {
  formatDate,
  formatRelativeTime,
  getStateColor,
  getStateLabel,
  getAgentColor,
  getAgentIcon,
} from '@/lib/utils';
import { formatSpecFeature, formatUserStory, labelTechStackKey } from '@/lib/product-spec';
import { CATEGORY_EMOJIS, CATEGORY_LABELS } from '@/lib/categories';
import { buildProductShareUrl, trackEvent } from '@/lib/analytics';

function BriefParagraphs({ text }: { text: string }) {
  return (
    <div className="text-sm text-gray-300 space-y-3">
      {text.split(/\n\n+/).map((para, pi) => (
        <p key={pi} className="leading-relaxed whitespace-pre-wrap">
          {para.split(/(\*\*[^*]+\*\*)/g).map((chunk, ci) =>
            chunk.startsWith('**') && chunk.endsWith('**') ? (
              <strong key={ci} className="text-white font-medium">
                {chunk.slice(2, -2)}
              </strong>
            ) : (
              <span key={ci}>{chunk}</span>
            )
          )}
        </p>
      ))}
    </div>
  );
}

// ── Category Helpers ─────────────────────────────────────────────────────

const getCategoryColor = (cat: string): string => {
  const colors: Record<string, string> = {
    ai_ml: 'info',
    devtools: 'success',
    fintech: 'warning',
    saas: 'warning',
    ecommerce: 'info',
    iot: 'info',
    security: 'error',
    productivity: 'success',
    analytics: 'info',
    automation: 'success',
    design: 'warning',
    communication: 'info',
    other: 'default',
    uncategorized: 'default',
  };
  return colors[cat] || 'default';
};

export default function ProductDetailPage() {
  const params = useParams();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sandboxStarting, setSandboxStarting] = useState(false);
  const [securityReport, setSecurityReport] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [briefOpenRole, setBriefOpenRole] = useState<string | null>('director');
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<number>(5);
  const [feedbackComment, setFeedbackComment] = useState<string>('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<{ ok: boolean; message?: string } | null>(null);
  const [journeyPromptOpen, setJourneyPromptOpen] = useState(false);
  const [journeyVote, setJourneyVote] = useState<'yes' | 'partial' | 'no' | null>(null);
  const [journeyNote, setJourneyNote] = useState('');
  const [journeySending, setJourneySending] = useState(false);

  useEffect(() => {
    if (params.id) {
      api
        .getProduct(params.id as string)
        .then(setProduct)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    }
  }, [params.id]);

  useEffect(() => {
    if (!product) return;
    trackEvent('product_view', { state: product.state }, product.id);
    void api.recordTelemetryEvent({
      product_id: product.id,
      event_type: 'product_view',
      data: { state: product.state },
      page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
      locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
    }).catch(() => {});
  }, [product?.id, product?.state]);

  const handleStartSandbox = async () => {
    if (!product || sandboxStarting) return;
    setSandboxStarting(true);
    trackEvent('sandbox_click', {}, product.id);
    void api.recordTelemetryEvent({
      product_id: product.id,
      event_type: 'sandbox_click',
      data: {},
      page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
      locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
    }).catch(() => {});
    try {
      const result = await api.startSandbox(product.id);
      setJourneyPromptOpen(true);
      // Open in current tab to avoid popup blockers.
      window.location.href = result.url;
    } catch (err: any) {
      console.error('Failed to start sandbox:', err);
      alert('Failed to start sandbox: ' + (err.message || 'Unknown error'));
    } finally {
      setSandboxStarting(false);
    }
  };

  const handleJourneySubmit = async () => {
    if (!product || !journeyVote || journeySending) return;
    setJourneySending(true);
    try {
      const rating = journeyVote === 'yes' ? 5 : journeyVote === 'partial' ? 3 : 1;
      await api.submitFeedback({
        product_id: product.id,
        rating,
        comment: journeyNote.trim() || `Journey vote: ${journeyVote}`,
        source: 'journey_prompt',
        journey_step: 'core_action',
        page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
        locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
        tags: ['nps', 'journey_prompt', journeyVote],
      });
      await api.recordTelemetryEvent({
        product_id: product.id,
        event_type: 'journey_feedback_submit',
        data: { vote: journeyVote, has_note: Boolean(journeyNote.trim()) },
        page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
        locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
      });
      setJourneyPromptOpen(false);
      setJourneyVote(null);
      setJourneyNote('');
    } catch {
      // ignore
    } finally {
      setJourneySending(false);
    }
  };

  const handleSubmitFeedback = async () => {
    if (!product || feedbackSending) return;
    if (!feedbackComment.trim()) {
      alert('Please write a short comment.');
      return;
    }
    setFeedbackSending(true);
    setFeedbackSent(null);
    try {
      const res = await api.submitFeedback({
        product_id: product.id,
        rating: feedbackRating,
        comment: feedbackComment.trim(),
        source: 'product_page',
        page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
        locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
        tags: [],
      });
      setFeedbackSent({ ok: true, message: res.message || 'Thanks!' });
      setFeedbackComment('');
      void api.recordTelemetryEvent({
        product_id: product.id,
        event_type: 'feedback_submit',
        data: { rating: feedbackRating, classification: res.classification },
        page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
        locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
      }).catch(() => {});
    } catch (e: any) {
      setFeedbackSent({ ok: false, message: e?.message || 'Failed to send feedback' });
    } finally {
      setFeedbackSending(false);
    }
  };

  const handleShareProduct = async () => {
    if (!product) return;
    const url = buildProductShareUrl(product.id);
    try {
      await navigator.clipboard.writeText(url);
      trackEvent('share_link', { channel: 'clipboard' }, product.id);
    } catch {
      trackEvent('share_link_failed', { reason: 'clipboard' }, product.id);
    }
  };

  const handleViewSecurityReport = async () => {
    if (!product || reportLoading) return;
    setReportLoading(true);
    try {
      const result = await api.getPublicSecurityReport(product.id);
      setSecurityReport(result.report);
      setShowReportModal(true);
    } catch (err: any) {
      console.error('Failed to load security report:', err);
      alert('No security report available for this product.');
    } finally {
      setReportLoading(false);
    }
  };

  const getGradeColor = (grade: string) => {
    switch ((grade || '')[0]) {
      case 'A': return 'text-emerald-400';
      case 'B': return 'text-blue-400';
      case 'C': return 'text-yellow-400';
      case 'D': return 'text-orange-400';
      case 'F': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading product...</p>
        </div>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <p className="text-red-400 text-lg mb-2">Failed to load product</p>
          <p className="text-gray-500 text-sm mb-4">{error}</p>
          <Button variant="secondary" onClick={() => (window.location.href = '/')}>
            Back to Home
          </Button>
        </div>
      </div>
    );
  }

  const pipelineProgress: Record<string, number> = {
    IDEA_RECEIVED: 0,
    SPEC_WRITTEN: 10,
    ARCH_DESIGNED: 20,
    CODE_COMMITTED: 30,
    QA_TESTING: 40,
    BUG_FOUND: 35,
    DEV_FIXING: 38,
    SECURITY_SCANNED: 50,
    MARKET_CONTENT_READY: 55,
    METHODOLOGY_REVIEWED: 58,
    SALES_ACTIVE: 70,
    SANDBOX_RUNNING: 80,
    TELEMETRY_COLLECTING: 90,
    EVOLUTION_ANALYZING: 100,
  };

  const progress = pipelineProgress[product.state as keyof typeof pipelineProgress] || 0;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="glass border-b border-white/10 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-sm">Back</span>
          </a>
          <div className="flex items-center gap-3">
            {/* Category Badge */}
            {product.category && (
              <Badge variant="info" className="text-xs">
                {CATEGORY_LABELS[product.category] || product.category}
              </Badge>
            )}
            <Badge
              variant={
                product.state === 'COMPLETED'
                  ? 'success'
                  : product.state === 'FAILED'
                  ? 'error'
                  : 'info'
              }
            >
              {getStateLabel(product.state)}
            </Badge>
            {product.delivery_profile === 'marketing_landing' && (
              <Badge variant="default" className="text-xs">
                Landing page
              </Badge>
            )}
            {product.delivery_profile === 'full_software' && (
              <Badge variant="success" className="text-xs">
                Full product
              </Badge>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Product Info */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <GlassCard className="mb-8">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h1 className="text-3xl font-bold text-white mb-2">
                  {product.name || product.spec?.product_name || 'Untitled Product'}
                </h1>
                {/* Selling Description */}
                {product.selling_description && (
                  <p className="text-gray-300 mb-2">{product.selling_description}</p>
                )}
                {product.storefront_stack_label && product.delivery_profile !== 'marketing_landing' && (
                  <p className="text-xs text-gray-500 mb-2" title={product.storefront_stack_label}>
                    Stack: {product.storefront_stack_label}
                  </p>
                )}
                <p className="text-gray-500 text-sm">
                  {product.spec?.description || product.idea}
                </p>
                {product.implementation_summary &&
                  Object.keys(product.implementation_summary).length > 0 &&
                  product.delivery_profile !== 'marketing_landing' && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {Object.entries(product.implementation_summary).map(([key, value]) => (
                        <span
                          key={key}
                          className="text-[11px] px-2.5 py-1 rounded-lg bg-indigo-500/15 text-indigo-200 border border-indigo-500/25"
                          title={`${labelTechStackKey(key)}: ${value}`}
                        >
                          <span className="text-indigo-400/90">{labelTechStackKey(key)}:</span>{' '}
                          <span className="text-gray-200">{value}</span>
                        </span>
                      ))}
                    </div>
                  )}
              </div>
              {/* Price Display */}
              {product.price_usdt != null && product.price_usdt > 0 && (
                <div className="text-right shrink-0">
                  <div className="text-2xl font-bold text-emerald-400">
                    ${product.price_usdt}
                    <span className="text-sm font-normal text-gray-400">/mo</span>
                  </div>
                  <div className="text-xs text-gray-500">starting from</div>
                  {product.price_tier && (
                    <Badge variant="info" className="text-[10px] mt-1 capitalize">
                      {product.price_tier}
                    </Badge>
                  )}
                </div>
              )}
            </div>

            {/* Progress */}
            <ProgressBar
              value={progress}
              label="Pipeline Progress"
              variant={product.state === 'FAILED' ? 'warning' : 'primary'}
              size="lg"
              className="mb-6"
            />

            {/* Meta Info */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Created</span>
                <p className="text-gray-300">{formatDate(product.created_at)}</p>
              </div>
              <div>
                <span className="text-gray-500">Product ID</span>
                <p className="text-gray-300 font-mono text-xs">{product.id}</p>
              </div>
              <div>
                <span className="text-gray-500">State</span>
                <p className="text-gray-300">{getStateLabel(product.state)}</p>
              </div>
              <div>
                <span className="text-gray-500">Target Audience</span>
                <p className="text-gray-300">
                  {product.spec?.target_audience || 'General'}
                </p>
              </div>
            </div>
          </GlassCard>
        </motion.div>

        {/* Marketplace Info Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08 }}
        >
          <GlassCard className="mb-8">
            <h2 className="text-xl font-semibold mb-4">
              <span className="mr-2">🛒</span> Marketplace
            </h2>

            {/* Category Badge */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm text-white/60">Category:</span>
              <Badge variant={getCategoryColor(product.category || '') as any}>
                <span className="mr-1">{CATEGORY_EMOJIS[product.category || ''] || '📦'}</span>
                {CATEGORY_LABELS[product.category || ''] || product.category || 'Uncategorized'}
              </Badge>
            </div>

            {/* Pricing */}
            {product.price_usdt != null && product.price_usdt > 0 && (
              <div className="mb-3">
                <span className="text-sm text-white/60">Pricing:</span>
                <span className="ml-2 text-lg font-bold text-emerald-400">
                  ${product.price_usdt}
                  <span className="text-sm font-normal text-white/40">/month</span>
                </span>
              </div>
            )}

            {/* Tags */}
            {product.tags && product.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {product.tags.map((tag: string, i: number) => (
                  <span
                    key={i}
                    className="text-xs px-2 py-1 rounded-full bg-white/5 text-white/60"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </GlassCard>
        </motion.div>

        {product.delivery_profile === 'marketing_landing' && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.085 }}
            className="mb-8"
          >
            <GlassCard className="border border-cyan-500/25 bg-cyan-950/20">
              <p className="text-sm text-gray-300 leading-relaxed">
                This SKU is a <span className="text-white font-medium">marketing landing page</span> (HTML/CSS/JS). We hide the full
                &quot;Implementation / stack&quot; block here because generated architecture text often describes a hypothetical production
                system — not what you preview in the iframe below.
              </p>
            </GlassCard>
          </motion.div>
        )}

        {/* Stakeholder brief — how the product was defined (idea → marketing → PM) */}
        {product.stakeholder_brief && product.stakeholder_brief.turns?.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.09 }}
          >
            <GlassCard className="mb-8">
              <div className="flex items-center gap-3 mb-2">
                <Users className="w-5 h-5 text-amber-400" />
                <h2 className="text-xl font-semibold text-white">How this product was defined</h2>
              </div>
              <p className="text-xs text-gray-500 mb-4">
                Synthesis of the pipeline inputs: strategy, go-to-market, and the PM specification (your technical
                contract for the build). Tap a card to read that perspective.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                {product.stakeholder_brief.turns.map((t) => {
                  const active = briefOpenRole === t.role;
                  const Icon =
                    t.role === 'marketing' ? Megaphone : t.role === 'pm' ? FileText : Users;
                  return (
                    <button
                      key={t.role}
                      type="button"
                      onClick={() => setBriefOpenRole((r) => (r === t.role ? null : t.role))}
                      className={`text-left rounded-xl border p-4 transition-all ${
                        active
                          ? 'border-amber-500/50 bg-amber-500/10'
                          : 'border-white/10 bg-white/[0.03] hover:border-white/20'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Icon className="w-4 h-4 text-amber-300 shrink-0" />
                        <span className="text-sm font-medium text-white">{t.display_name}</span>
                      </div>
                      <p className="text-[11px] text-gray-500 leading-snug">{t.title}</p>
                    </button>
                  );
                })}
              </div>
              {briefOpenRole && (
                <div className="rounded-xl border border-white/10 bg-black/20 p-4">
                  {product.stakeholder_brief.turns
                    .filter((t) => t.role === briefOpenRole)
                    .map((t) => (
                      <div key={t.role}>
                        <h3 className="text-sm font-medium text-amber-200/90 mb-2">{t.title}</h3>
                        <BriefParagraphs text={t.body} />
                      </div>
                    ))}
                </div>
              )}
              {product.stakeholder_brief.footer_note && (
                <p className="text-[11px] text-gray-600 mt-4">{product.stakeholder_brief.footer_note}</p>
              )}
            </GlassCard>
          </motion.div>
        )}

        {/* Demo / sandbox quality */}
        {product.demo_quality && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.095 }}
          >
            <GlassCard className="mb-8">
              <div className="flex items-center gap-3 mb-2">
                <Zap className="w-5 h-5 text-lime-400" />
                <h2 className="text-xl font-semibold text-white">Demo & sandbox quality</h2>
              </div>
              <p className="text-xs text-gray-500 mb-4">
                Heuristic checks on generated <code className="text-gray-400">index.html</code> vs the specification.
                A blank iframe is often missing CSS (wrong paths) — we inject a base URL for relative assets.
              </p>
              <div className="flex flex-wrap items-center gap-6 mb-4">
                <div className="text-center">
                  <div className={`text-3xl font-bold ${getGradeColor(product.demo_quality.grade)}`}>
                    {product.demo_quality.grade}
                  </div>
                  <div className="text-[10px] text-gray-500">Grade</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-white">{product.demo_quality.score}/100</div>
                  <div className="text-[10px] text-gray-500">Score</div>
                </div>
                {product.demo_quality.spec_coverage_pct != null && (
                  <div>
                    <div className="text-2xl font-bold text-cyan-300">
                      ~{product.demo_quality.spec_coverage_pct}%
                    </div>
                    <div className="text-[10px] text-gray-500">Spec terms on landing page</div>
                  </div>
                )}
                <Badge variant={product.demo_quality.sandbox_ready ? 'success' : 'warning'}>
                  {product.demo_quality.sandbox_ready ? 'Ready for preview' : 'Needs content fixes'}
                </Badge>
              </div>
              {product.demo_quality.issues?.length > 0 && (
                <ul className="space-y-2 text-sm text-gray-400">
                  {product.demo_quality.issues.map((issue, i) => (
                    <li key={i} className="flex gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>{issue.detail}</span>
                    </li>
                  ))}
                </ul>
              )}
              {product.browser_preview_e2e && (
                <div className="mt-4 rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-xs">
                  <p className="text-gray-400 mb-1 font-medium text-indigo-200/90">Headless browser (Chromium)</p>
                  <p className="text-gray-500">
                    {(product.browser_preview_e2e as any).skipped
                      ? 'Skipped (AIFACTORY_BROWSER_E2E=0).'
                      : (product.browser_preview_e2e as any).passed
                      ? `Passed — visible text ~${(product.browser_preview_e2e as any).visible_text_length ?? '?'} chars${
                          (product.browser_preview_e2e as any).ui_interaction &&
                          !(product.browser_preview_e2e as any).ui_interaction.skipped
                            ? `; UI clicks OK (${(product.browser_preview_e2e as any).ui_interaction.clicks_attempted ?? 0})`
                            : ''
                        }.`
                      : `Failed — ${((product.browser_preview_e2e as any).issues || []).slice(0, 3).join('; ') || (product.browser_preview_e2e as any).error || 'see QA report'}`}
                  </p>
                  {product.qa_gates_all_passed != null && (
                    <p className="text-gray-600 mt-1">
                      Last QA combined gates (static + browser):{' '}
                      {product.qa_gates_all_passed ? 'passed' : 'failed'}
                    </p>
                  )}
                </div>
              )}
            </GlassCard>
          </motion.div>
        )}

        {/* Spec Section */}
        {product.spec && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <GlassCard className="mb-8">
              <div className="flex items-center gap-3 mb-4">
                <FileText className="w-5 h-5 text-indigo-400" />
                <h2 className="text-xl font-semibold text-white">Specification</h2>
              </div>
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-gray-400 mb-2">Core Features</h3>
                  <ul className="space-y-1">
                    {product.spec.core_features?.map((feature: unknown, i: number) => (
                      <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span className="whitespace-pre-wrap">{formatSpecFeature(feature)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-400 mb-2">User Stories</h3>
                  <ul className="space-y-1">
                    {product.spec.user_stories?.map((story: unknown, i: number) => (
                      <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                        <span className="text-indigo-400 mt-0.5">•</span>
                        <span className="whitespace-pre-wrap">{formatUserStory(story)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}


        {/* Implementation: full-software only — marketing landings ship a single page; architect stack is illustrative */}
        {product.architecture && product.delivery_profile !== 'marketing_landing' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.22 }}
          >
            <GlassCard className="mb-8">
              <div className="flex items-center gap-3 mb-2">
                <Layers className="w-5 h-5 text-cyan-400" />
                <h2 className="text-xl font-semibold text-white">Implementation</h2>
              </div>
              <p className="text-xs text-gray-500 mb-6">
                How this product is built: technologies, services, deployment and integration points (from the generated
                architecture document).
              </p>

              {(product.architecture.architecture_name || product.architecture.overview) && (
                <div className="mb-6">
                  {product.architecture.architecture_name && (
                    <h3 className="text-sm font-medium text-white mb-1">{product.architecture.architecture_name}</h3>
                  )}
                  {product.architecture.overview && (
                    <p className="text-sm text-gray-400 leading-relaxed">{product.architecture.overview}</p>
                  )}
                </div>
              )}

              {product.architecture.tech_stack && Object.keys(product.architecture.tech_stack).length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                    <Package className="w-4 h-4 text-indigo-400" />
                    Stack & technologies
                  </h3>
                  <div className="grid sm:grid-cols-2 gap-3">
                    {Object.entries(product.architecture.tech_stack).map(([key, value]) => (
                      <div
                        key={key}
                        className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 flex flex-col gap-0.5"
                      >
                        <span className="text-[10px] uppercase tracking-wide text-gray-500">
                          {labelTechStackKey(key)}
                        </span>
                        <span className="text-sm text-gray-200">{value as string}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {product.architecture.deployment && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                    <Server className="w-4 h-4 text-emerald-400" />
                    Deployment & ops
                  </h3>
                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-2 text-sm">
                    {product.architecture.deployment.type && (
                      <p>
                        <span className="text-gray-500">Type: </span>
                        <span className="text-gray-200 font-mono text-xs">{product.architecture.deployment.type}</span>
                      </p>
                    )}
                    {product.architecture.deployment.scaling && (
                      <p>
                        <span className="text-gray-500">Scaling: </span>
                        <span className="text-gray-300">{product.architecture.deployment.scaling}</span>
                      </p>
                    )}
                    {product.architecture.deployment.requirements &&
                      Array.isArray(product.architecture.deployment.requirements) &&
                      product.architecture.deployment.requirements.length > 0 && (
                        <div>
                          <span className="text-gray-500 text-xs">Requirements</span>
                          <ul className="mt-1 list-disc list-inside text-gray-300 text-sm space-y-0.5">
                            {product.architecture.deployment.requirements.map((r: string, i: number) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                  </div>
                </div>
              )}

              {product.architecture.components && product.architecture.components.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                    <Code2 className="w-4 h-4 text-purple-400" />
                    Services & components
                  </h3>
                  <div className="grid gap-3">
                    {product.architecture.components.map((comp: any, i: number) => (
                      <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                          <span className="text-sm font-medium text-white">{comp.name}</span>
                          {(comp.technology || comp.type) && (
                            <Badge variant="info" className="text-[10px] font-mono">
                              {comp.technology || comp.type}
                            </Badge>
                          )}
                        </div>
                        {comp.description && <p className="text-xs text-gray-500 mb-2">{comp.description}</p>}
                        {comp.responsibilities && Array.isArray(comp.responsibilities) && comp.responsibilities.length > 0 && (
                          <ul className="text-xs text-gray-400 space-y-1 list-disc list-inside">
                            {comp.responsibilities.map((line: string, j: number) => (
                              <li key={j}>{line}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {product.architecture.data_models && product.architecture.data_models.length > 0 && (
                <details className="mb-6 group rounded-xl border border-white/10 bg-black/20">
                  <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-300 flex items-center gap-2 list-none [&::-webkit-details-marker]:hidden">
                    <Database className="w-4 h-4 text-amber-400" />
                    Data layer ({product.architecture.data_models.length} models)
                  </summary>
                  <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
                    {product.architecture.data_models.map((dm: any, i: number) => (
                      <div key={i} className="text-sm">
                        <span className="text-white font-medium">{dm.name}</span>
                        {dm.fields && Array.isArray(dm.fields) && (
                          <p className="text-xs text-gray-500 mt-1 font-mono">{dm.fields.join(', ')}</p>
                        )}
                        {dm.relationships && (
                          <p className="text-xs text-gray-500 mt-0.5">{dm.relationships}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {product.architecture.api_endpoints && product.architecture.api_endpoints.length > 0 && (
                <details className="rounded-xl border border-white/10 bg-black/20">
                  <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-300 list-none [&::-webkit-details-marker]:hidden">
                    API surface ({product.architecture.api_endpoints.length} endpoints)
                  </summary>
                  <div className="px-4 pb-4 overflow-x-auto border-t border-white/5 pt-3">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="text-gray-500 border-b border-white/10">
                          <th className="py-2 pr-3 font-medium">Method</th>
                          <th className="py-2 pr-3 font-medium">Path</th>
                          <th className="py-2 font-medium">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {product.architecture.api_endpoints.slice(0, 24).map((ep: any, i: number) => (
                          <tr key={i} className="border-b border-white/5 text-gray-400">
                            <td className="py-2 pr-3 font-mono text-indigo-300 whitespace-nowrap">{ep.method}</td>
                            <td className="py-2 pr-3 font-mono text-gray-300 whitespace-nowrap">{ep.path}</td>
                            <td className="py-2 text-gray-500">{ep.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {product.architecture.api_endpoints.length > 24 && (
                      <p className="text-[10px] text-gray-600 mt-2">
                        Showing 24 of {product.architecture.api_endpoints.length} endpoints.
                      </p>
                    )}
                  </div>
                </details>
              )}
            </GlassCard>
          </motion.div>
        )}

        {/* Evolution History */}
        {product.evolution_history && product.evolution_history.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <GlassCard className="mb-8">
              <div className="flex items-center gap-3 mb-4">
                <BarChart3 className="w-5 h-5 text-emerald-400" />
                <h2 className="text-xl font-semibold text-white">Evolution History</h2>
              </div>
              <div className="space-y-4">
                {product.evolution_history.map((entry: any, i: number) => (
                  <div key={i} className="glass p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-400">
                        {formatDate(entry.created_at)}
                      </span>
                      <Badge variant={entry.health_score > 80 ? 'success' : 'warning'}>
                        Score: {entry.health_score}
                      </Badge>
                    </div>
                    {entry.improvements?.length > 0 && (
                      <div className="mt-2">
                        <span className="text-xs text-gray-500">Improvements:</span>
                        <ul className="mt-1 space-y-1">
                          {entry.improvements.map((imp: string, j: number) => (
                            <li key={j} className="text-xs text-gray-400 flex items-start gap-1">
                              <span className="text-emerald-400">↑</span>
                              {imp}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* Actions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="flex flex-wrap gap-4"
        >
          <Button
            icon={<ShoppingCart className="w-4 h-4" />}
            onClick={() => {
              trackEvent('checkout_click', { placement: 'product_actions' }, product.id);
              window.location.href = `/checkout?product=${product.id}`;
            }}
          >
            Purchase with Crypto
          </Button>
          <Button
            variant="secondary"
            icon={<Share2 className="w-4 h-4" />}
            onClick={handleShareProduct}
          >
            Copy share link
          </Button>
          <Button
            variant="secondary"
            icon={sandboxStarting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
            onClick={handleStartSandbox}
            disabled={sandboxStarting}
          >
            {sandboxStarting ? 'Starting...' : 'View in Sandbox'}
          </Button>
          <Button
            variant="secondary"
            icon={reportLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            onClick={handleViewSecurityReport}
            disabled={reportLoading}
          >
            {reportLoading ? 'Loading...' : 'Security Report'}
          </Button>
          <Button
            variant="secondary"
            icon={<Bot className="w-4 h-4" />}
            onClick={() => {
              setFeedbackOpen(true);
              void api
                .recordTelemetryEvent({
                  product_id: product.id,
                  event_type: 'feedback_open',
                  data: {},
                  page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
                  locale: typeof navigator !== 'undefined' ? navigator.language : undefined,
                })
                .catch(() => {});
            }}
          >
            Leave feedback
          </Button>
        </motion.div>

        {journeyPromptOpen && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4"
          >
            <GlassCard className="border border-indigo-500/25 bg-indigo-950/20">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h3 className="text-sm font-medium text-white">Quick journey check</h3>
                <span className="text-xs text-gray-400">Did this product help you achieve your goal?</span>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                {[
                  { id: 'yes', label: 'Yes, worked great' },
                  { id: 'partial', label: 'Partially' },
                  { id: 'no', label: 'No, blocked' },
                ].map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    onClick={() => setJourneyVote(o.id as any)}
                    className={`text-xs px-3 py-1.5 rounded-lg border ${
                      journeyVote === o.id
                        ? 'border-indigo-400/60 bg-indigo-500/15 text-indigo-200'
                        : 'border-white/10 bg-white/[0.03] text-gray-300'
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <textarea
                value={journeyNote}
                onChange={(e) => setJourneyNote(e.target.value)}
                className="w-full min-h-[72px] rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                placeholder="Optional: what blocked you or what should be improved?"
              />
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setJourneyPromptOpen(false)}>Skip</Button>
                <Button onClick={handleJourneySubmit} disabled={!journeyVote || journeySending}>
                  {journeySending ? 'Sending…' : 'Send journey feedback'}
                </Button>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* Feedback Modal */}
        {feedbackOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={() => setFeedbackOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-[#0d0d2b] border border-white/10 rounded-2xl max-w-xl w-full overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-white/10">
                <h2 className="text-lg font-semibold text-white">Feedback</h2>
                <button
                  onClick={() => setFeedbackOpen(false)}
                  className="text-gray-500 hover:text-white transition-colors"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <p className="text-xs text-gray-500 mb-2">Rating</p>
                  <div className="flex items-center gap-2">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setFeedbackRating(n)}
                        className={`h-9 w-9 rounded-lg border text-sm ${
                          feedbackRating >= n
                            ? 'border-amber-400/60 bg-amber-500/15 text-amber-200'
                            : 'border-white/10 bg-white/[0.03] text-gray-400 hover:border-white/20'
                        }`}
                        aria-label={`Set rating ${n}`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-2">What should we improve?</p>
                  <textarea
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    className="w-full min-h-[120px] rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                    placeholder="Tell us what you expected, what happened, and (if it’s a bug) steps to reproduce."
                  />
                </div>
                {feedbackSent && (
                  <div
                    className={`text-xs rounded-lg border px-3 py-2 ${
                      feedbackSent.ok
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                        : 'border-red-500/30 bg-red-500/10 text-red-200'
                    }`}
                  >
                    {feedbackSent.message}
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={() => setFeedbackOpen(false)}>
                    Close
                  </Button>
                  <Button
                    onClick={handleSubmitFeedback}
                    disabled={feedbackSending}
                    icon={feedbackSending ? <Loader2 className="w-4 h-4 animate-spin" /> : undefined}
                  >
                    {feedbackSending ? 'Sending…' : 'Send feedback'}
                  </Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}

        {/* Security Report Modal */}
        {showReportModal && securityReport && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowReportModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-[#0d0d2b] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between p-6 border-b border-white/10">
                <div className="flex items-center gap-3">
                  <Shield className="w-6 h-6 text-indigo-400" />
                  <h2 className="text-lg font-semibold text-white">Security Report</h2>
                </div>
                <button
                  onClick={() => setShowReportModal(false)}
                  className="text-gray-500 hover:text-white transition-colors"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-6 space-y-6">
                {/* Grade & Score */}
                <div className="flex items-center gap-6">
                  {securityReport.grade && (
                    <div className="text-center">
                      <div className={`text-4xl font-bold ${getGradeColor(securityReport.grade)}`}>
                        {securityReport.grade}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">Grade</div>
                    </div>
                  )}
                  {securityReport.security_score !== undefined && (
                    <div className="text-center">
                      <div className="text-3xl font-bold text-indigo-400">
                        {securityReport.security_score}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">Score</div>
                    </div>
                  )}
                  {securityReport.risk_level && (
                    <div className="text-center">
                      <Badge
                        variant={
                          securityReport.risk_level === 'critical' || securityReport.risk_level === 'high'
                            ? 'error'
                            : securityReport.risk_level === 'medium'
                            ? 'info'
                            : 'success'
                        }
                      >
                        {securityReport.risk_level}
                      </Badge>
                      <div className="text-xs text-gray-500 mt-1">Risk Level</div>
                    </div>
                  )}
                </div>

                {/* Vulnerabilities / Findings */}
                {(securityReport.vulnerabilities || securityReport.findings) && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-3">
                      Findings ({securityReport.vulnerabilities?.length || securityReport.findings?.length || 0})
                    </h3>
                    <div className="space-y-2">
                      {(securityReport.vulnerabilities || securityReport.findings || []).slice(0, 50).map((v: any, vi: number) => (
                        <div key={vi} className="p-3 rounded-xl bg-white/5 border border-white/5">
                          <div className="flex items-center gap-2 mb-1">
                            <Badge
                              variant={
                                v.severity === 'critical' || v.severity === 'high'
                                  ? 'error'
                                  : v.severity === 'medium'
                                  ? 'info'
                                  : 'success'
                              }
                              className="text-[10px]"
                            >
                              {v.severity || v.type || 'info'}
                            </Badge>
                            <span className="text-sm text-gray-300 font-medium">
                              {v.title || v.description || v.id || `Finding #${vi + 1}`}
                            </span>
                          </div>
                          {v.description && v.description !== v.title && (
                            <p className="text-xs text-gray-500 ml-1">{v.description}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Summary / Raw fields */}
                {securityReport.summary && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">Summary</h3>
                    <p className="text-sm text-gray-400">{securityReport.summary}</p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
