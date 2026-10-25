'use client';

import React, { useEffect, useRef, useState } from 'react';
import { rememberSiteLocale, storedSiteLocale } from '@/lib/siteLocale';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { csrfHeaders } from '@/lib/csrf';
import { getGuestPhraseBlockReason } from '@/lib/promptSafety';
import { LandingStylePresetPicker } from '@/components/landing/LandingStylePresetPicker';
import { TrustMetricsStrip } from '@/components/TrustMetricsStrip';
import { formatBenchmarkRate, formatBenchmarkTrend } from '@/lib/formatBenchmark';

import {
  Sparkles,
  Cpu,
  Shield,
  Zap,
  ArrowRight,
  Star,
  ChevronRight,
  ChevronDown,
  Bot,
  Code2,
  TestTube,
  Rocket,
  BarChart3,
  Coins,
  Menu,
  X,
  BookOpen,
  ExternalLink,
  Github,
  Settings,
  Home,
  FileText,
  Info,
  ScrollText,
  Layers,
  Tag,
  DollarSign,
  ShoppingCart,
  Search,
  RefreshCw,
  AlertCircle,
  Package,
  Palette,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import api from '@/lib/api';
import {
  getMarketingStrings,
  saveMarketingLocale,
  type MarketingLocale,
  type MarketingStrings,
} from '@/lib/marketing';
import { HeroVisualShowcase } from '@/components/marketing/HeroVisualShowcase';
import { ArchitectureOrbit } from '@/components/landing/ArchitectureOrbit';
import { LogosEcosystemSection } from '@/components/landing/LogosEcosystemSection';
import { VisitorStart, VisitorCatalog, VisitorNext } from '@/components/storefront/VisitorWorkspace';
import { visitorJourney } from '@/lib/visitorJourney';
import { ecosystemNavigation } from '@/lib/ecosystemNavigation';

const FEATURE_ICONS = {
  sparkles: Sparkles,
  bot: Bot,
  shield: Shield,
  rocket: Rocket,
  chart: BarChart3,
  coins: Coins,
} as const;

// ── Navigation Bar ────────────────────────────────────────────────────────

function Navbar({
  copy,
  locale,
  onLocaleChange,
}: {
  copy: MarketingStrings;
  locale: MarketingLocale;
  onLocaleChange: (l: MarketingLocale) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreWrapRef = useRef<HTMLDivElement>(null);

  const navLinksPrimary = [
    { label: copy.navGenerateLanding, href: '#hero-generate', icon: Sparkles },
    { label: copy.navExplore, href: '/explore', icon: Layers },
    { label: copy.navProducts, href: '#products', icon: Bot },
    { label: copy.navDocs, href: '/docs', icon: BookOpen },
    { label: visitorJourney[locale].demo, href: '/admin?tab=dashboard', icon: Settings },
  ];

  const navLinksMore = [
    ...ecosystemNavigation(locale).links.map(link => ({ ...link, icon: ExternalLink })),
    { label: copy.navHome, href: '/', icon: Home },
    { label: copy.navFactoryIq, href: '/iq', icon: TrendingUp },
    { label: copy.navFeatures, href: '#features', icon: Star },
    { label: copy.navAbout, href: '/about', icon: Info },
    { label: copy.navUpdates, href: '/updates', icon: ScrollText },
    { label: copy.navBlog, href: '/blog', icon: BookOpen },
    { label: copy.navLaunchKit, href: '/launch-kit', icon: Rocket },
    { label: copy.navBadge, href: '/badge', icon: Tag },
    { label: copy.navIdea, href: '/lead', icon: Package },
    { label: copy.navBenchmark, href: '/benchmark', icon: BarChart3 },
  ];

  const navLinksMobile = [...navLinksPrimary, ...navLinksMore];

  useEffect(() => {
    if (!moreOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (moreWrapRef.current && !moreWrapRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  return (
    <nav className="glass border-b border-white/5 min-w-0 bg-black/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2 min-w-0">
        {/* Logo — shrink-0 keeps chip + wordmark on-screen when the row is tight */}
        <Link href="/" className="flex items-center gap-2 group min-w-0 shrink-0 max-w-[calc(100%-3.5rem)]">
          <Cpu className="w-6 h-6 text-indigo-400 group-hover:text-indigo-300 transition-colors shrink-0" />
          <span className="text-lg font-bold text-white truncate">{copy.brandName}</span>
        </Link>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-3 lg:gap-4 whitespace-nowrap">
          {navLinksPrimary.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors shrink-0 whitespace-nowrap"
            >
              <link.icon className="w-4 h-4 shrink-0" />
              <span className="whitespace-nowrap">{link.label}</span>
            </a>
          ))}
          <div className="relative shrink-0" ref={moreWrapRef}>
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors py-1 whitespace-nowrap"
            >
              <span>{copy.navMore}</span>
              <ChevronDown className={`w-4 h-4 transition-transform ${moreOpen ? 'rotate-180' : ''}`} />
            </button>
            {moreOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-2 min-w-[13rem] rounded-xl border border-white/10 bg-black/95 backdrop-blur-xl py-2 shadow-xl z-[60]"
              >
                {navLinksMore.map((link) => (
                  <a
                    key={link.label}
                    role="menuitem"
                    href={link.href}
                    onClick={() => setMoreOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors whitespace-nowrap"
                  >
                    <link.icon className="w-4 h-4 shrink-0 opacity-80" />
                    {link.label}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0" aria-label="Language">
          {(['en', 'ru', 'es', 'fr', 'zh'] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => onLocaleChange(code)}
              className={`rounded-md px-2 py-1 text-xs font-medium uppercase transition-colors ${
                locale === code ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-white/10 hover:text-white'
              }`}
            >
              {code}
            </button>
          ))}
        </div>

        {/* Mobile Menu Toggle */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden text-gray-400 hover:text-white transition-colors shrink-0 p-1 -mr-1"
          aria-label="Toggle menu"
        >
          {menuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Menu */}
      {menuOpen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:hidden border-t border-white/5 bg-black/90 backdrop-blur-xl"
        >
          <div className="px-4 py-3 space-y-2">
            {navLinksMobile.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 text-sm text-gray-400 hover:text-white py-2 transition-colors"
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </a>
            ))}
          </div>
        </motion.div>
      )}
    </nav>
  );
}

// ── Status Banner ────────────────────────────────────────────────────────

function StatusBanner({ copy }: { copy: MarketingStrings }) {
  const [inFlight, setInFlight] = useState<number | null>(null);
  const [shipped, setShipped] = useState<number | null>(null);

  useEffect(() => {
    let stale = false;
    fetch('/api/public/pipeline-status')
      .then((r) => r.json())
      .then((d: { products_in_pipeline?: number; products_shipped?: number }) => {
        if (stale) return;
        setInFlight(typeof d.products_in_pipeline === 'number' ? d.products_in_pipeline : 0);
        setShipped(typeof d.products_shipped === 'number' ? d.products_shipped : 0);
      })
      .catch(() => {});
    return () => { stale = true; };
  }, []);

  const inFlightText =
    inFlight !== null ? copy.statusBannerInPipeline.replace('{n}', String(inFlight)) : '';
  const shippedText =
    shipped !== null ? copy.statusBannerShipped.replace('{n}', String(shipped)) : '';

  if (inFlight === null && shipped === null) return null;

  return (
    <div className="border-b border-indigo-500/20 bg-gradient-to-r from-indigo-950/70 via-black/80 to-fuchsia-950/70">
      <div className="max-w-7xl mx-auto px-3 py-2 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs sm:text-sm">
        <span className="font-semibold text-amber-400/90 tracking-wide">
          {copy.statusBannerPreLaunch}
        </span>
        <span className="text-gray-400 inline-flex items-center gap-1">
          <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
          {inFlightText || '...'}
        </span>
        <span className="text-gray-400 inline-flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          {shippedText || '...'}
        </span>
      </div>
    </div>
  );
}

// ── Hero Section ─────────────────────────────────────────────────────────

function FeaturesSection({ copy }: { copy: MarketingStrings }) {
  const features = copy.features.map((f) => ({
    ...f,
    icon: FEATURE_ICONS[f.iconKey],
  }));

  return (
    <section className="py-24 px-4" id="features">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-gradient-primary">{copy.featuresIntroGradientWord}</span>{' '}
            <span className="text-white">{copy.featuresIntroRest}</span>
          </h2>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            {copy.featuresIntroSubtitle}
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
            >
              <GlassCard className="h-full">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${feature.gradient} p-2.5 mb-4`}>
                  <feature.icon className="w-full h-full text-white" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-sm leading-relaxed">{feature.description}</p>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Pipeline Section ─────────────────────────────────────────────────────

function PipelineSection({ copy }: { copy: MarketingStrings }) {
  const steps = [
    { name: 'Research', icon: Sparkles, color: 'from-indigo-500 to-purple-500' },
    { name: 'Spec', icon: Code2, color: 'from-purple-500 to-pink-500' },
    { name: 'Marketing', icon: Layers, color: 'from-pink-500 to-rose-500' },
    { name: 'Architect', icon: Cpu, color: 'from-rose-500 to-orange-500' },
    { name: 'Design', icon: Palette, color: 'from-fuchsia-500 to-violet-500' },
    { name: 'Develop', icon: Bot, color: 'from-orange-500 to-yellow-500' },
    { name: 'QA', icon: Shield, color: 'from-emerald-500 to-teal-500' },
    { name: 'Launch', icon: Rocket, color: 'from-cyan-500 to-blue-500' },
  ];

  return (
    <section className="py-24 px-4" id="pipeline">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-white">{copy.pipelineSectionTitle}</h2>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">{copy.pipelineSectionSubtitle}</p>
        </motion.div>

        <div className="relative">
          {/* Pipeline line */}
          <div className="absolute top-12 left-0 right-0 h-0.5 bg-gradient-to-r from-indigo-500 via-fuchsia-500 to-cyan-500 hidden lg:block" />

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-4">
            {steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="text-center"
              >
                <div className={`w-16 h-16 mx-auto mb-3 rounded-2xl bg-gradient-to-br ${step.color} p-3 relative z-10 glass-card ring-1 ring-white/10`}>
                  <step.icon className="w-full h-full text-white" />
                </div>
                <p className="text-sm text-gray-400 font-medium">{step.name}</p>
              </motion.div>
            ))}
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.45, delay: 0.15 }}
          className="mt-12 max-w-xl mx-auto"
        >
          <GlassCard className="p-6 md:p-8 text-center border border-fuchsia-500/25 bg-gradient-to-b from-fuchsia-500/10 to-transparent shadow-[0_0_48px_-16px_rgba(192,38,211,0.35)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-fuchsia-300/90 mb-2">
              {copy.pipelineDesignerEyebrow}
            </p>
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-fuchsia-500 to-violet-600 p-3 ring-2 ring-white/10">
              <Palette className="w-full h-full text-white" />
            </div>
            <h3 className="text-lg md:text-xl font-semibold text-white mb-2">{copy.pipelineDesignerTitle}</h3>
            <p className="text-sm text-gray-400 leading-relaxed">{copy.pipelineDesignerBody}</p>
          </GlassCard>
        </motion.div>
      </div>
    </section>
  );
}

async function readApiErrorMessage(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d))
      return d
        .map((x) => (typeof x === 'object' && x && 'msg' in x ? String((x as { msg: string }).msg) : String(x)))
        .join(' ');
  } catch {
    /* ignore */
  }
  return res.statusText || 'Request failed';
}

function PipelineBuildSection({ copy }: { copy: MarketingStrings }) {
  const router = useRouter();
  const [slogan, setSlogan] = useState('');
  const [stylePresetId, setStylePresetId] = useState('');
  const [guestLoading, setGuestLoading] = useState(false);
  const [guestError, setGuestError] = useState<string | null>(null);

  const continueToAdmin = () => {
    const t = slogan.trim();
    try {
      if (t) sessionStorage.setItem('aicom_prefill_idea', t);
    } catch {
      /* ignore */
    }
    router.push('/admin?tab=new-product');
  };

  const guestBuildLanding = async () => {
    const t = slogan.trim();
    setGuestError(null);
    if (t.length < 8) {
      setGuestError(copy.heroPhraseTooShort);
      return;
    }
    const inj = getGuestPhraseBlockReason(t);
    if (inj) {
      setGuestError(inj);
      return;
    }
    setGuestLoading(true);
    try {
      const res = await fetch('/api/public/generate-landing', {
        method: 'POST',
        // The CSRF middleware enforces on the presence of a session cookie, not on the path,
        // so this public CTA returned 403 for every visitor who had one — which on the demo
        // host is everyone who clicked "Open demo". See lib/analytics.ts for the same trap.
        headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
        body: JSON.stringify({
          phrase: t,
          fast_path: true,
          ...(stylePresetId ? { preset_id: stylePresetId } : {}),
        }),
      });
      if (!res.ok) {
        setGuestError(await readApiErrorMessage(res));
        return;
      }
      const data = (await res.json()) as { product_id?: string };
      if (!data.product_id) {
        setGuestError('Invalid response from server.');
        return;
      }
      router.push(`/product/${data.product_id}`);
    } catch (e) {
      setGuestError(e instanceof Error ? e.message : 'Network error');
    } finally {
      setGuestLoading(false);
    }
  };

  return (
    <div className="mt-6">
        <motion.div
          id="pipeline-build-form"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="mb-12 md:mb-14"
        >
          <p className="text-center text-[11px] md:text-xs font-semibold uppercase tracking-[0.25em] text-fuchsia-300/95 mb-3">
            {copy.heroGeneratorEyebrow}
          </p>
          <GlassCard className="relative overflow-hidden p-6 md:p-10 text-left border-2 border-fuchsia-500/35 shadow-[0_0_60px_-12px_rgba(217,70,239,0.45)] ring-1 ring-white/10 bg-gradient-to-b from-white/[0.07] to-transparent">
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-gradient-to-br from-fuchsia-600/20 to-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
            <h2 className="relative text-2xl md:text-3xl lg:text-4xl font-bold text-white mb-2 text-center leading-tight">
              {copy.heroGeneratorTitle}
            </h2>
            <label className="relative block text-sm font-medium text-gray-200 mb-2 mt-6">
              {copy.heroSloganLineLabel}
            </label>
            <div className="relative flex flex-col sm:flex-row gap-3 sm:items-stretch">
              <input
                type="text"
                value={slogan}
                maxLength={2000}
                onChange={(e) => {
                  setSlogan(e.target.value);
                  if (guestError) setGuestError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !guestLoading) {
                    e.preventDefault();
                    void guestBuildLanding();
                  }
                }}
                className="relative flex-1 min-w-0 rounded-xl bg-black/50 border border-fuchsia-500/25 px-4 py-3.5 text-base text-white placeholder:text-gray-500 focus:outline-hidden focus:ring-2 focus:ring-fuchsia-500/50 shadow-inner"
                placeholder={copy.heroSloganLinePlaceholder}
                autoComplete="off"
                aria-invalid={!!guestError}
              />
              <Button
                size="lg"
                loading={guestLoading}
                className="w-full sm:w-auto shrink-0 justify-center text-base font-semibold shadow-lg shadow-fuchsia-900/40 bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 border-0 sm:px-8"
                icon={<Sparkles className="w-5 h-5" />}
                onClick={() => void guestBuildLanding()}
              >
                {copy.heroGuestBuildCta}
              </Button>
            </div>
            <LandingStylePresetPicker
              value={stylePresetId}
              onChange={setStylePresetId}
              autoLabel={copy.heroStylePresetAuto}
              label={copy.heroStylePresetLabel}
              hint={copy.heroStylePresetHint}
              className="relative mt-4"
              selectClassName="relative w-full rounded-xl bg-black/50 border border-fuchsia-500/20 px-4 py-3 text-sm text-white focus:outline-hidden focus:ring-2 focus:ring-fuchsia-500/40"
            />
            <p className="relative text-xs text-gray-400 mt-3 leading-relaxed">{copy.heroGuestHelp}</p>
            <p className="relative text-xs text-gray-400 mt-2 mb-4 leading-relaxed">{copy.heroPricingLine}</p>
            {guestError && (
              <p className="relative text-sm text-red-400 mb-4 flex items-start gap-2" role="alert">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {guestError}
              </p>
            )}
            <div className="relative flex flex-col sm:flex-row sm:items-center gap-3 pt-1 border-t border-white/10">
              <button
                type="button"
                onClick={continueToAdmin}
                className="text-sm text-fuchsia-200/90 hover:text-white text-left underline-offset-4 hover:underline"
              >
                {copy.heroCtaPhrase}
              </button>
              <span className="hidden sm:inline text-gray-600">·</span>
              <button
                type="button"
                onClick={() => router.push('/admin')}
                className="text-sm text-gray-400 hover:text-white text-left underline-offset-4 hover:underline"
              >
                {copy.heroCtaAdminOnly}
              </button>
            </div>
          </GlassCard>
        </motion.div>
    </div>
  );
}

function TrustBlock() {
  const [m, setM] = useState<any>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api
      .getPublicBenchmark()
      .then((x) => {
        setM(x.investor_metrics);
        setSrc(x.investor_metrics_source ?? 'benchmark_scorecard');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  return (
    <section className="px-4 py-12">
      <div className="max-w-5xl mx-auto rounded-2xl border border-white/10 bg-white/5 p-6">
        <h3 className="text-white font-semibold mb-2">Quality Trust Block</h3>
        <p className="text-sm text-gray-400 mb-4">
          Live benchmark-based quality metrics from production pipeline.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <Metric k="Latest" v={m?.latest_pass_rate} format="rate" loading={loading} />
          <Metric k="7d rolling" v={m?.rolling_7d_pass_rate} format="rate" loading={loading} />
          <Metric k="Trend" v={m?.trend_vs_7d} format="trend" loading={loading} />
          <Metric k="Readiness" v={m?.production_readiness_index} format="rate" loading={loading} />
        </div>
        <p className="mt-4 text-[11px] leading-relaxed text-gray-500">
          {loading
            ? 'Loading metrics…'
            : src === 'pipeline_storefront_proxy'
              ? 'Estimated from storefront-eligible completed builds — benchmark league scorecard has no runs yet. See Benchmark page after league jobs populate data/reports/benchmark_scorecard.json.'
              : src === 'pipeline_storefront_proxy_supplement'
                ? 'Benchmark scorecard lists runs but pass-rate averages are still 0 — showing storefront readiness among completed builds as a clearer live snapshot.'
                : 'Sourced from benchmark scorecard (Director / league runs).'}
        </p>
      </div>
    </section>
  );
}

function Metric({
  k,
  v,
  format,
  loading,
}: {
  k: string;
  v: any;
  format: 'rate' | 'trend';
  loading?: boolean;
}) {
  const display = loading ? '…' : format === 'trend' ? formatBenchmarkTrend(v) : formatBenchmarkRate(v);
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="text-gray-500 text-xs">{k}</div>
      <div className="text-cyan-300 font-semibold tabular-nums">{display}</div>
    </div>
  );
}

// ── Footer ───────────────────────────────────────────────────────────────

function Footer({ copy, locale }: { copy: MarketingStrings; locale: MarketingLocale }) {
  const footerLinks = [
    ...ecosystemNavigation(locale).links.map(link => ({ ...link, icon: ExternalLink })),
    { label: copy.footerDocumentation, href: '/docs', icon: FileText },
    { label: copy.footerBlog, href: '/blog', icon: BookOpen },
    { label: copy.footerLaunchKit, href: '/launch-kit', icon: Rocket },
    { label: copy.footerTerms, href: '/terms', icon: FileText },
    { label: copy.footerPrivacy, href: '/privacy', icon: Shield },
    { label: copy.navFactoryIq, href: '/iq', icon: TrendingUp },
    { label: copy.footerBadge, href: '/badge', icon: Tag },
    { label: copy.footerApiReference, href: '/api/docs', icon: Code2 },
    { label: copy.footerGithub, href: 'https://github.com/alexar76/aicom', icon: Github },
    { label: copy.footerAdminPanel, href: '/admin', icon: Settings },
  ];

  return (
    <footer className="border-t border-white/5 px-4 pt-8 pb-[var(--storefront-footer-pad)] md:pb-8">
      <div className="mx-auto flex max-w-6xl min-w-0 flex-col gap-6 md:flex-row md:items-start md:justify-between md:gap-8">
        <div className="flex shrink-0 items-center justify-center gap-2 md:justify-start">
          <Cpu className="h-5 w-5 shrink-0 text-indigo-400" aria-hidden />
          <span className="text-center text-sm text-gray-400 md:text-left">{copy.footerTagline}</span>
        </div>
        <div className="flex min-w-0 w-full max-w-full flex-col gap-3 md:min-w-0 md:flex-1 md:items-end">
          <nav
            className="flex w-full min-w-0 flex-wrap justify-center gap-2 sm:gap-2.5 md:justify-end"
            aria-label="Site footer"
          >
            {footerLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="inline-flex min-h-[44px] min-w-0 max-w-full flex-[1_1_9.5rem] items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-center text-sm font-medium leading-snug text-gray-200 transition hover:border-white/20 hover:bg-white/[0.08] hover:text-white active:bg-white/[0.12] sm:flex-[1_1_10.5rem] md:min-h-0 md:max-w-[13rem] md:flex-[0_1_auto] md:justify-start md:rounded-lg md:border-transparent md:bg-transparent md:px-2.5 md:py-1.5 md:font-normal md:text-gray-500 md:hover:text-gray-300"
                target={link.href.startsWith('http') ? '_blank' : undefined}
                rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
              >
                <link.icon className="h-4 w-4 shrink-0 md:h-3.5 md:w-3.5" aria-hidden />
                <span className="min-w-0 text-pretty">{link.label}</span>
              </a>
            ))}
          </nav>
          <p className="text-center text-xs text-gray-600 md:text-right">© 2026 AI-Factory</p>
        </div>
      </div>
    </footer>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────

export default function HomePage({ initialLocale, explicitLocale = false }: { initialLocale: MarketingLocale; explicitLocale?: boolean }) {
  // Resolved on the server (app/page.tsx: cookie, else Accept-Language), so the server render
  // and hydration agree. Detecting it here during the first render cost React #418 for every
  // non-English visitor: the server rendered 'en', the browser rendered 'ru', and React threw
  // the server tree away.
  const [mktLocale, setMktLocale] = useState<MarketingLocale>(initialLocale);
  const siteCopy = getMarketingStrings(mktLocale);
  useEffect(() => {
    const revealHashTarget = () => {
      const id = window.location.hash.slice(1);
      if (!id) return;
      const target = document.getElementById(id);
      if (!target) return;
      const details = target.closest('details');
      if (details) {
        details.open = true;
        requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
      }
    };
    revealHashTarget();
    window.addEventListener('hashchange', revealHashTarget);
    return () => window.removeEventListener('hashchange', revealHashTarget);
  }, []);


  // A choice saved before the cookie existed lives only in localStorage, which the server
  // cannot read: adopt it after hydration and save it where the server looks next time.
  useEffect(() => {
    const adopt = () => {
      const stored = storedSiteLocale();
      if (!stored) return;
      setMktLocale(stored);
      rememberSiteLocale(stored);
    };
    if (explicitLocale) saveMarketingLocale(initialLocale);
    else adopt();
    window.addEventListener('marketing-locale-changed', adopt);
    return () => window.removeEventListener('marketing-locale-changed', adopt);
  }, [explicitLocale, initialLocale]);

  useEffect(() => {
    document.documentElement.lang = mktLocale;
  }, [mktLocale]);

  const handleLocaleChange = (code: MarketingLocale) => {
    setMktLocale(code);
    saveMarketingLocale(code);
    const url = new URL(window.location.href);
    url.searchParams.set('lang', code);
    window.history.replaceState(null, '', url);
  };

  return (
    <main className="min-w-0 overflow-x-clip">
      <div className="sticky top-0 z-50 min-w-0">
        <StatusBanner copy={siteCopy} />
        <Navbar copy={siteCopy} locale={mktLocale} onLocaleChange={handleLocaleChange} />
      </div>
      <nav aria-label={ecosystemNavigation(mktLocale).current} className="border-b border-white/10 bg-slate-950/70 px-4 py-3">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <span className="text-gray-400">{ecosystemNavigation(mktLocale).current}</span>
          {ecosystemNavigation(mktLocale).links.map(link => (
            <a key={link.href} href={link.href} className="inline-flex min-h-8 items-center gap-1 text-cyan-300 hover:text-white">
              {link.label}<ExternalLink size={14} aria-hidden />
            </a>
          ))}
        </div>
      </nav>
      <VisitorStart locale={mktLocale} />
      <details id="factory-build" className="scroll-mt-40 mx-auto mb-8 max-w-4xl rounded-2xl border border-white/10 px-4 py-5">
        <summary className="cursor-pointer text-lg font-semibold text-gray-200">{visitorJourney[mktLocale].pipelineBuild}</summary>
        <PipelineBuildSection copy={siteCopy} />
      </details>
      <VisitorCatalog locale={mktLocale} />
      <VisitorNext locale={mktLocale} />
      <details className="mx-auto mb-12 max-w-6xl rounded-2xl border border-white/10 px-4 py-5">
        <summary className="cursor-pointer px-2 text-lg font-semibold text-gray-200">{visitorJourney[mktLocale].technical}</summary>
        <HeroVisualShowcase eyebrow={siteCopy.heroVisualEyebrow} title={siteCopy.heroVisualTitle} caption={siteCopy.heroVisualCaption} watchLabel={siteCopy.heroWatchDemo} />
        <TrustMetricsStrip />
        <TrustBlock />
        <FeaturesSection copy={siteCopy} />
        <PipelineSection copy={siteCopy} />
        <ArchitectureOrbit copy={siteCopy} />
        <LogosEcosystemSection copy={siteCopy} />
      </details>
      <Footer copy={siteCopy} locale={mktLocale} />
    </main>
  );
}
