'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
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
import { Input } from '@/components/ui/Input';
import api, { Product } from '@/lib/api';
import { useStorefrontCatalog } from '@/hooks/useStorefrontCatalog';
import { labelTechStackKey } from '@/lib/product-spec';
import { formatRelativeTime, getStateLabel } from '@/lib/utils';
import {
  detectMarketingLocale,
  getMarketingStrings,
  saveMarketingLocale,
  type MarketingLocale,
  type MarketingStrings,
} from '@/lib/marketing';
import { HeroVisualShowcase } from '@/components/marketing/HeroVisualShowcase';
import { getGuestPhraseBlockReason } from '@/lib/promptSafety';
import { ArchitectureOrbit } from '@/components/landing/ArchitectureOrbit';
import { formatBenchmarkRate, formatBenchmarkTrend } from '@/lib/formatBenchmark';

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
    { label: copy.navAdmin, href: '/admin', icon: Settings },
  ];

  const navLinksMore = [
    { label: copy.navHome, href: '#', icon: Home },
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
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-white/5 min-w-0">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2 min-w-0">
        {/* Logo — shrink-0 keeps chip + wordmark on-screen when the row is tight */}
        <a href="/" className="flex items-center gap-2 group min-w-0 shrink-0 max-w-[calc(100%-3.5rem)]">
          <Cpu className="w-6 h-6 text-indigo-400 group-hover:text-indigo-300 transition-colors shrink-0" />
          <span className="text-lg font-bold text-white truncate">{copy.brandName}</span>
        </a>

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
          {(['en', 'ru', 'es'] as const).map((code) => (
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

function HeroSection({ copy }: { copy: MarketingStrings }) {
  const router = useRouter();
  const [slogan, setSlogan] = useState('');
  const [guestLoading, setGuestLoading] = useState(false);
  const [guestError, setGuestError] = useState<string | null>(null);

  const continueToAdmin = () => {
    const t = slogan.trim();
    try {
      if (t) sessionStorage.setItem('aicom_prefill_idea', t);
    } catch {
      /* ignore */
    }
    window.location.href = '/admin?tab=new-product';
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phrase: t }),
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
    <section className="relative min-h-screen flex flex-col justify-center px-4 pt-20 pb-12">
      {/* Background effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/25 rounded-full blur-[128px]" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-fuchsia-500/15 rounded-full blur-[128px]" />
      </div>

      <div className="relative max-w-4xl mx-auto w-full">
        {/* ── 1. Landing generator FIRST (most visible) ───────────────────── */}
        <HeroVisualShowcase
          eyebrow={copy.heroVisualEyebrow}
          title={copy.heroVisualTitle}
          caption={copy.heroVisualCaption}
          watchLabel={copy.heroWatchDemo}
        />

        <motion.div
          id="hero-generate"
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
                className="relative flex-1 min-w-0 rounded-xl bg-black/50 border border-fuchsia-500/25 px-4 py-3.5 text-base text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-fuchsia-500/50 shadow-inner"
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
                onClick={() => (window.location.href = '/admin')}
                className="text-sm text-gray-400 hover:text-white text-left underline-offset-4 hover:underline"
              >
                {copy.heroCtaAdminOnly}
              </button>
            </div>
          </GlassCard>
        </motion.div>

        {/* ── 2. Brand + pitch (below generator; marketplace lives further down) ── */}
        <div className="text-center max-w-3xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08 }}
            className="mb-5"
          >
            <Badge variant="info" className="text-xs px-3 py-1.5">
              <Sparkles className="w-3.5 h-3.5 mr-1" />
              {copy.heroBadge}
            </Badge>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.12 }}
            className="text-4xl md:text-6xl font-bold mb-5"
          >
            <span className="text-gradient">{copy.heroTitleLead}</span>{' '}
            <span className="text-white">{copy.heroTitleRest}</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.16 }}
            className="text-base md:text-lg text-gray-400 mb-4 leading-relaxed"
          >
            {copy.heroSubtitle}
          </motion.p>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="text-sm text-indigo-200/75 max-w-2xl mx-auto mb-10"
          >
            {copy.heroHint}
          </motion.p>
        </div>

        {/* Secondary CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.22 }}
          className="flex flex-wrap gap-4 justify-center mb-14"
        >
          <Button
            variant="secondary"
            size="lg"
            icon={<BarChart3 className="w-5 h-5" />}
            onClick={() => {
              const el = document.getElementById('products');
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            {copy.ctaSecondary}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            icon={<Zap className="w-5 h-5" />}
            onClick={() => (window.location.href = '/admin')}
          >
            {copy.ctaPrimary}
          </Button>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.26 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto"
        >
          {[
            { label: copy.stats.agents, value: copy.stats.agentsValue, icon: Bot },
            { label: copy.stats.pipeline, value: copy.stats.pipelineValue, icon: Code2 },
            { label: copy.stats.llm, value: copy.stats.llmValue, icon: Cpu },
            { label: copy.stats.chains, value: copy.stats.chainsValue, icon: Coins },
          ].map((stat, i) => (
            <div key={i} className="text-center">
              <stat.icon className="w-6 h-6 text-indigo-400 mx-auto mb-2" />
              <div className="text-2xl font-bold text-white">{stat.value}</div>
              <div className="text-sm text-gray-500">{stat.label}</div>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

// ── Features Section ─────────────────────────────────────────────────────

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

// ── Products Section ─────────────────────────────────────────────────────

// ── Category Helpers ─────────────────────────────────────────────────────

const CATEGORY_ICONS: Record<string, string> = {
  landings: 'layout',
  ai_ml: 'brain',
  devtools: 'code',
  fintech: 'wallet',
  saas: 'cloud',
  ecommerce: 'shopping-cart',
  iot: 'cpu',
  security: 'shield',
  productivity: 'zap',
};

const CATEGORY_LABELS: Record<string, string> = {
  landings: 'Landing pages',
  ai_ml: 'AI/ML',
  devtools: 'DevTools',
  fintech: 'FinTech',
  saas: 'SaaS',
  ecommerce: 'E-Commerce',
  iot: 'IoT',
  security: 'Security',
  productivity: 'Productivity',
};

const CATEGORY_EMOJIS: Record<string, string> = {
  landings: '🎯',
  ai_ml: '🧠',
  devtools: '🛠️',
  fintech: '💰',
  saas: '☁️',
  ecommerce: '🛒',
  iot: '📡',
  security: '🔒',
  productivity: '⚡',
  uncategorized: '📁',
};

const CATEGORY_COLORS: Record<string, string> = {
  landings: 'from-sky-500 to-indigo-500',
  ai_ml: 'from-purple-500 to-indigo-500',
  devtools: 'from-blue-500 to-cyan-500',
  fintech: 'from-emerald-500 to-teal-500',
  saas: 'from-orange-500 to-yellow-500',
  ecommerce: 'from-pink-500 to-rose-500',
  iot: 'from-cyan-500 to-blue-500',
  security: 'from-red-500 to-orange-500',
  productivity: 'from-violet-500 to-purple-500',
};

const getCategoryColor = (cat: string): string => {
  const colors: Record<string, string> = {
    landings: 'info',
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

// ── Skeleton Card ────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="glass-card p-6 space-y-4">
      {/* Header skeleton */}
      <div className="space-y-2">
        <div className="skeleton h-5 w-4/5 rounded" />
        <div className="flex gap-2">
          <div className="skeleton h-5 w-16 rounded-full" />
          <div className="skeleton h-5 w-20 rounded-full" />
        </div>
      </div>
      {/* Description skeleton */}
      <div className="space-y-2">
        <div className="skeleton h-3 w-full rounded" />
        <div className="skeleton h-3 w-4/5 rounded" />
      </div>
      {/* Tags skeleton */}
      <div className="flex gap-2">
        <div className="skeleton h-6 w-16 rounded-full" />
        <div className="skeleton h-6 w-20 rounded-full" />
        <div className="skeleton h-6 w-14 rounded-full" />
      </div>
      {/* Footer skeleton */}
      <div className="flex items-center justify-between pt-3 border-t border-white/5">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-8 w-24 rounded-xl" />
      </div>
    </div>
  );
}

function CatalogProductCard({
  product,
  index,
  getProductName,
  getProductDescription,
}: {
  product: Product;
  index: number;
  getProductName: (p: Product) => string;
  getProductDescription: (p: Product) => string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.05 }}
    >
      <Link
        href={`/product/${product.id}`}
        className="block h-full rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400/80"
      >
        <GlassCard
          hover
          glow={product.state === 'COMPLETED'}
          className={`h-full flex flex-col ${
            product.delivery_profile === 'marketing_landing'
              ? 'ring-1 ring-fuchsia-500/20 border-fuchsia-500/15'
              : 'ring-1 ring-emerald-500/15 border-emerald-500/10'
          }`}
        >
          <div className="mb-3 space-y-2">
            <h3
              className="text-lg font-semibold leading-snug text-[color:var(--text-primary)] line-clamp-2"
              title={getProductName(product)}
            >
              {getProductName(product)}
            </h3>
            <div className="flex flex-wrap items-center gap-1.5">
              {product.is_template && (
                <Badge variant="warning" className="text-[10px]">
                  Template
                </Badge>
              )}
              <Badge variant={getCategoryColor(product.category || '') as any} className="text-[10px]">
                {CATEGORY_LABELS[product.category || ''] || product.category || 'Uncategorized'}
              </Badge>
              {product.delivery_profile === 'marketing_landing' ? (
                <Badge variant="default" className="text-[10px]">
                  Landing
                </Badge>
              ) : (
                <Badge variant="success" className="text-[10px]">
                  {product.delivery_profile === 'full_software' ? 'Full product' : 'Full stack'}
                </Badge>
              )}
            </div>
          </div>

          <p className="mb-3 line-clamp-2 text-sm text-[color:var(--text-secondary)]">{getProductDescription(product)}</p>

          {product.implementation_summary && Object.keys(product.implementation_summary).length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-4">
              {Object.entries(product.implementation_summary)
                .slice(0, 4)
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="max-w-[160px] truncate rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]"
                    title={`${labelTechStackKey(k)}: ${v}`}
                  >
                    <span className="text-[color:var(--text-muted)] opacity-70">{labelTechStackKey(k)}:</span> {v}
                  </span>
                ))}
              {Object.keys(product.implementation_summary).length > 4 && (
                <span className="text-[10px] text-[color:var(--text-muted)] opacity-80">
                  +{Object.keys(product.implementation_summary).length - 4}
                </span>
              )}
            </div>
          )}

          {product.tags && product.tags.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {product.tags.slice(0, 3).map((tag: string, ti: number) => (
                <span key={ti} className="rounded-full bg-white/5 px-2 py-1 text-xs text-[color:var(--text-secondary)]">
                  {tag}
                </span>
              ))}
              {product.tags.length > 3 && (
                <span className="text-xs text-[color:var(--text-muted)]">+{product.tags.length - 3}</span>
              )}
            </div>
          )}

          <div className="flex-1" />

          <div className="flex items-center justify-between pt-3 border-t border-white/5">
            <div className="flex items-center gap-3">
              {product.price_usdt != null && product.price_usdt > 0 && (
                <span className="text-sm font-semibold text-emerald-400">
                  ${product.price_usdt}
                  <span className="text-[10px] font-normal text-[color:var(--text-muted)]">/mo</span>
                </span>
              )}
            </div>
            <span className="inline-flex items-center rounded-xl border border-transparent px-4 py-2 text-sm font-medium text-[color:var(--text-secondary)]">
              Details →
            </span>
          </div>
        </GlassCard>
      </Link>
    </motion.div>
  );
}

// ── Products Section ─────────────────────────────────────────────────────

function ProductsSection({ copy }: { copy: MarketingStrings }) {
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const {
    products,
    categories,
    catalogTotalCount,
    loading,
    refreshing,
    fromCache,
    error,
    revalidate,
  } = useStorefrontCatalog(activeCategory);

  const handleCategoryChange = (catId: string) => {
    setActiveCategory(catId);
    setSearchQuery('');
  };

  const handleRetry = () => {
    revalidate();
  };

  // Client-side search filter
  const filteredProducts = products.filter((p) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const stackStr = p.implementation_summary
      ? Object.values(p.implementation_summary).join(' ').toLowerCase()
      : '';
    return (
      (p.name || '').toLowerCase().includes(q) ||
      ((p as any).description || '').toLowerCase().includes(q) ||
      (p.selling_description || '').toLowerCase().includes(q) ||
      (p.tags || []).some((tag: string) => tag.toLowerCase().includes(q)) ||
      stackStr.includes(q)
    );
  });

  const landingExamples = filteredProducts.filter((p) => p.delivery_profile === 'marketing_landing');
  const fullExamples = filteredProducts.filter((p) => p.delivery_profile !== 'marketing_landing');

  // Derive the display name for a product
  const getProductName = (product: Product): string => {
    return product.name || product.spec?.product_name || product.idea || 'Product';
  };

  // Derive the display description for a product
  const getProductDescription = (product: Product): string => {
    return product.selling_description || product.spec?.description || (product as any).description || product.idea || '';
  };

  return (
    <section className="py-24 px-4" id="products">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-white">{copy.productsTitle}</span>
          </h2>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            {copy.productsSubtitle}
          </p>
          {refreshing && products.length > 0 && (
            <p className="mt-3 inline-flex items-center gap-2 text-xs text-gray-500">
              <RefreshCw className="h-3.5 w-3.5 animate-spin text-indigo-400/80" aria-hidden />
              {fromCache ? 'Showing cached catalog — updating…' : 'Updating catalog…'}
            </p>
          )}
        </motion.div>

        {/* Search Bar */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-md mx-auto mb-8"
        >
          <Input
            placeholder="Search products..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </motion.div>

        {/* Category Tabs */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex flex-wrap justify-center gap-2 mb-10"
        >
          <motion.button
            onClick={() => handleCategoryChange('all')}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300 ${
              activeCategory === 'all'
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shadow-lg shadow-indigo-500/10'
                : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10 hover:text-gray-300'
            }`}
          >
            <Layers className="w-3.5 h-3.5 inline-block mr-1.5" />
            All
            <span className="ml-1.5 text-xs opacity-60">
              ({catalogTotalCount})
            </span>
          </motion.button>
          {categories.map((cat) => (
            <motion.button
              key={cat.id}
              onClick={() => handleCategoryChange(cat.id)}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300 ${
                activeCategory === cat.id
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shadow-lg shadow-indigo-500/10'
                  : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10 hover:text-gray-300'
              }`}
            >
              <span className="mr-1.5">{CATEGORY_EMOJIS[cat.id] || '📦'}</span>
              {CATEGORY_LABELS[cat.id] || cat.name}
              <span className="ml-1.5 text-xs opacity-60">({cat.product_count})</span>
            </motion.button>
          ))}
        </motion.div>

        {/* Error State — only when there is nothing to show from cache */}
        {error && !loading && products.length === 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center py-16"
          >
            <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
            <p className="text-red-400 text-lg mb-2">Failed to load products</p>
            <p className="text-gray-500 text-sm mb-6">{error}</p>
            <Button
              variant="secondary"
              icon={<RefreshCw className="w-4 h-4" />}
              onClick={handleRetry}
            >
              Retry
            </Button>
          </motion.div>
        )}

        {/* Loading State */}
        {loading && !error && (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && filteredProducts.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            {searchQuery ? (
              <>
                <Search className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400 text-lg mb-2">No results found</p>
                <p className="text-gray-500 text-sm mb-6">
                  No products match &ldquo;{searchQuery}&rdquo;. Try a different search term.
                </p>
                <Button variant="ghost" onClick={() => setSearchQuery('')}>
                  Clear Search
                </Button>
              </>
            ) : (
              <>
                <Package className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400 text-lg mb-2">No products in this category yet</p>
                <p className="text-gray-500 text-sm mb-6">
                  {activeCategory !== 'all' ? (
                    <>Try selecting a different category or check back later.</>
                  ) : (
                    <>
                      Submit an idea through the{' '}
                      <a href="/admin" className="text-indigo-400 hover:text-indigo-300 underline">
                        Admin Panel
                      </a>{' '}
                      or CLI to get started.
                    </>
                  )}
                </p>
                {activeCategory !== 'all' && (
                  <Button
                    variant="secondary"
                    onClick={() => handleCategoryChange('all')}
                  >
                    View All Products
                  </Button>
                )}
              </>
            )}
          </motion.div>
        )}

        {/* Product grids — landings vs full stacks */}
        {!loading && !error && filteredProducts.length > 0 && (
          <div className="space-y-16">
            <div>
              <div className="flex flex-wrap items-baseline justify-between gap-3 mb-2">
                <h3 className="text-2xl md:text-3xl font-bold text-white">{copy.productsLandingsTitle}</h3>
                <span className="text-xs font-mono text-fuchsia-300/90 bg-fuchsia-500/10 border border-fuchsia-500/25 rounded-lg px-2.5 py-1">
                  {landingExamples.length} listing{landingExamples.length === 1 ? '' : 's'}
                </span>
              </div>
              <p className="text-gray-500 text-sm max-w-3xl mb-8">{copy.productsLandingsSubtitle}</p>
              {landingExamples.length === 0 ? (
                <p className="text-gray-600 text-sm border border-white/5 rounded-xl px-4 py-6 bg-white/[0.02]">
                  No marketing landings match this search or category — try &quot;All&quot;, clear search, or open{' '}
                  <Link href="/explore/landings" className="text-fuchsia-300/90 hover:text-fuchsia-200 underline">
                    Landing pages
                  </Link>
                  .
                </p>
              ) : (
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {landingExamples.map((product, i) => (
                    <CatalogProductCard
                      key={product.id}
                      product={product}
                      index={i}
                      getProductName={getProductName}
                      getProductDescription={getProductDescription}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-white/10 pt-16">
              <div className="flex flex-wrap items-baseline justify-between gap-3 mb-2">
                <h3 className="text-2xl md:text-3xl font-bold text-white">{copy.productsFullTitle}</h3>
                <span className="text-xs font-mono text-emerald-300/90 bg-emerald-500/10 border border-emerald-500/25 rounded-lg px-2.5 py-1">
                  {fullExamples.length} listing{fullExamples.length === 1 ? '' : 's'}
                </span>
              </div>
              <p className="text-gray-500 text-sm max-w-3xl mb-8">{copy.productsFullSubtitle}</p>
              {fullExamples.length === 0 ? (
                <p className="text-gray-600 text-sm border border-white/5 rounded-xl px-4 py-6 bg-white/[0.02]">
                  No full products match this filter — try another category or queue a build from{' '}
                  <Link href="/admin" className="text-emerald-300/90 hover:text-emerald-200 underline">
                    Admin
                  </Link>
                  .
                </p>
              ) : (
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {fullExamples.map((product, i) => (
                    <CatalogProductCard
                      key={product.id}
                      product={product}
                      index={i}
                      getProductName={getProductName}
                      getProductDescription={getProductDescription}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// ── CTA Section ──────────────────────────────────────────────────────────

function CTASection({ copy }: { copy: MarketingStrings }) {
  return (
    <section className="py-24 px-4">
      <div className="max-w-4xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          className="glass-strong rounded-3xl p-12 md:p-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold mb-4 text-white">
            {copy.ctaBannerTitle}
          </h2>
          <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">
            {copy.ctaBannerSubtitle}
          </p>
          <div className="flex flex-wrap gap-4 justify-center">
            <Button
              size="lg"
              icon={<Zap className="w-5 h-5" />}
              onClick={() => (window.location.href = '/admin')}
            >
              {copy.ctaBannerPrimary}
            </Button>
            <Button
              variant="secondary"
              size="lg"
              icon={<BookOpen className="w-5 h-5" />}
              onClick={() => (window.location.href = '/docs')}
            >
              {copy.ctaBannerSecondary}
            </Button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function SeoFaqSection() {
  const faqs = [
    {
      q: 'What does AI-Factory generate?',
      a: 'Primarily share-ready marketing landings from the public phrase box; the same pipeline also produces full_software builds (APIs, persistence, compose-friendly repos) when work is queued from Admin or Director.',
    },
    {
      q: 'Can I run multiple ideas at once?',
      a: 'Yes, batch mode supports up to 10 ideas with progress tracking and retry support.',
    },
    {
      q: 'How does quality control work?',
      a: 'Quality uses benchmark pass-rate metrics, release gates, and continuous pipeline checks.',
    },
    {
      q: 'Do you support paid upgrades?',
      a: 'Yes. Free tier limits are visible in account, and paid plans upgrade through Stripe checkout.',
    },
  ];
  return (
    <section className="py-16 px-4">
      <div className="max-w-5xl mx-auto">
        <h3 className="text-3xl font-bold text-white mb-6">FAQ</h3>
        <div className="grid md:grid-cols-2 gap-4">
          {faqs.map((f) => (
            <div key={f.q} className="rounded-xl border border-white/10 bg-white/5 p-5">
              <p className="text-white font-semibold mb-2">{f.q}</p>
              <p className="text-gray-400 text-sm">{f.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
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

function Footer({ copy }: { copy: MarketingStrings }) {
  const footerLinks = [
    { label: copy.footerDocumentation, href: '/docs', icon: FileText },
    { label: copy.footerBlog, href: '/blog', icon: BookOpen },
    { label: copy.footerLaunchKit, href: '/launch-kit', icon: Rocket },
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

export default function HomePage() {
  const [mktLocale, setMktLocale] = useState<MarketingLocale>(() => detectMarketingLocale());
  const siteCopy = getMarketingStrings(mktLocale);

  const handleLocaleChange = (code: MarketingLocale) => {
    setMktLocale(code);
    saveMarketingLocale(code);
  };

  return (
    <main className="min-w-0 overflow-x-clip">
      <Navbar copy={siteCopy} locale={mktLocale} onLocaleChange={handleLocaleChange} />
      <StatusBanner copy={siteCopy} />
      <HeroSection copy={siteCopy} />
      <FeaturesSection copy={siteCopy} />
      <PipelineSection copy={siteCopy} />
      <ArchitectureOrbit copy={siteCopy} />
      <ProductsSection copy={siteCopy} />
      <TrustBlock />
      <SeoFaqSection />
      <CTASection copy={siteCopy} />
      <Footer copy={siteCopy} />
    </main>
  );
}
