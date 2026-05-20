/**
 * Public-site marketing copy — global launch is English-first.
 */

import { MARKETING_ES } from './marketing-es';
import { MARKETING_RU } from './marketing-ru';

export type MarketingLocale = 'en' | 'ru' | 'es';

export type MarketingStrings = {
  brandName: string;
  /** Navbar anchor to #hero-generate */
  navGenerateLanding: string;
  navExplore: string;
  navProducts: string;
  navDocs: string;
  navAdmin: string;
  navMore: string;
  navHome: string;
  navFeatures: string;
  navAbout: string;
  navUpdates: string;
  navBlog: string;
  navLaunchKit: string;
  navBadge: string;
  navIdea: string;
  navBenchmark: string;
  heroBadge: string;
  /** Above-the-fold visual hook (video + landing shots) — must render before text wall */
  heroVisualEyebrow: string;
  heroVisualTitle: string;
  heroVisualCaption: string;
  heroWatchDemo: string;
  heroTitleLead: string;
  heroTitleRest: string;
  heroSubtitle: string;
  heroHint: string;
  /** Above-the-fold landing generator (must stay visually first in hero) */
  heroGeneratorEyebrow: string;
  heroGeneratorTitle: string;
  heroPhraseTitle: string;
  heroPhrasePlaceholder: string;
  heroSloganLineLabel: string;
  heroSloganLinePlaceholder: string;
  heroPricingLine: string;
  heroGuestBuildCta: string;
  heroGuestHelp: string;
  heroPhraseTooShort: string;
  heroCtaPhrase: string;
  heroCtaAdminOnly: string;
  /** Pre-launch status banner on homepage */
  statusBannerPreLaunch: string;
  statusBannerInPipeline: string;
  statusBannerShipped: string;
  ctaPrimary: string;
  ctaSecondary: string;
  stats: {
    agents: string;
    agentsValue: string;
    pipeline: string;
    pipelineValue: string;
    llm: string;
    llmValue: string;
    chains: string;
    chainsValue: string;
  };
  featuresIntroGradientWord: string;
  featuresIntroRest: string;
  featuresIntroSubtitle: string;
  features: {
    title: string;
    description: string;
    gradient: string;
    iconKey:
      | 'sparkles'
      | 'bot'
      | 'shield'
      | 'rocket'
      | 'chart'
      | 'coins';
  }[];
  productsTitle: string;
  productsSubtitle: string;
  /** Home marketplace: brochure HTML/CSS builds */
  productsLandingsTitle: string;
  productsLandingsSubtitle: string;
  /** Home marketplace: apps / APIs / compose stacks */
  productsFullTitle: string;
  productsFullSubtitle: string;
  ctaBannerTitle: string;
  ctaBannerSubtitle: string;
  ctaBannerPrimary: string;
  ctaBannerSecondary: string;
  footerTagline: string;
  footerDocumentation: string;
  footerBlog: string;
  footerLaunchKit: string;
  footerBadge: string;
  footerApiReference: string;
  footerGithub: string;
  footerAdminPanel: string;
  /** Mid-page pipeline strip (home) */
  pipelineSectionTitle: string;
  pipelineSectionSubtitle: string;
  /** Investor-facing callout: UX layer (Architect `ui_experience` → Developer) */
  pipelineDesignerEyebrow: string;
  pipelineDesignerTitle: string;
  pipelineDesignerBody: string;
  /** Architecture orbit diagram (home) */
  architectureEyebrow: string;
  architectureTitle: string;
  architectureSubtitle: string;
  architectureHubLabel: string;
  architectureHubRoles: string;
  architectureHubFooter: string;
  architectureNodes: readonly { label: string; sub: string }[];
};

const EN: MarketingStrings = {
  brandName: 'AI-Factory',
  navGenerateLanding: 'Generate landing',
  navExplore: 'Explore',
  navProducts: 'Products',
  navDocs: 'Docs',
  navAdmin: 'Admin',
  navMore: 'More',
  navHome: 'Home',
  navFeatures: 'Features',
  navAbout: 'About',
  navUpdates: 'Updates',
  navBlog: 'Blog',
  navLaunchKit: 'Launch Kit',
  navBadge: 'Badge',
  navIdea: 'Idea',
  navBenchmark: 'Benchmark',
  heroBadge: 'One factory — crisp landings in a phrase, full applications from Admin',
  heroVisualEyebrow: 'Watch the factory in action',
  heroVisualTitle: 'Idea → agents → shippable product — full walkthrough on YouTube',
  heroVisualCaption: 'Product demo and pipeline tour:',
  heroWatchDemo: 'Open on YouTube',
  heroTitleLead: 'Launch-ready pages',
  heroTitleRest: 'and real apps — from the same brief',
  heroSubtitle:
    'Try the line above for a fast, shareable marketing page you can preview after QA — ideal for promos, waitlists, and “show me something real” moments. When scope grows into APIs, data, auth, and multi-screen products, the same agent pipeline runs deeper builds from Admin or Director. Sandbox preview and optional on-chain checkout apply to both paths.',
  heroHint:
    'Below: live examples from brochure landings to full-stack listings. The phrase box is intentionally light; Admin is where complex work queues — one engine, not a toy “lite” stack.',
  heroGeneratorEyebrow: 'Start here — guest try-out (landing-first)',
  heroGeneratorTitle: 'Type what you need. We ship a page you can preview.',
  heroPhraseTitle: 'Your phrase → a polished marketing page',
  heroPhrasePlaceholder:
    'e.g. Neon SaaS waitlist for an AI scheduling tool — hero, 3 benefits, pricing cards, footer with links…',
  heroSloganLineLabel: 'Slogan or one-line business brief',
  heroSloganLinePlaceholder:
    'e.g. Luxury leather wallets D2C — hero, craftsmanship story, 3 reasons to buy, email capture, footer',
  heroPricingLine:
    'One click queues a page you can track · sandbox after QA · optional checkout — or switch to Admin when you need a full application instead.',
  heroGuestBuildCta: 'Build business landing',
  heroGuestHelp:
    'Guests: no login. This path optimizes for a single credible page. For multi-tenant apps, backends, integrations, and long-lived products, open Admin — same agents and gates, richer delivery profile.',
  heroPhraseTooShort: 'Use at least 8 characters so the brief is concrete.',
  heroCtaPhrase: 'Open admin with this text',
  heroCtaAdminOnly: 'Advanced — admin only',
  statusBannerPreLaunch: 'v0.1 — pre-launch',
  statusBannerInPipeline: '{n} in pipeline',
  statusBannerShipped: '{n} shipped',
  ctaPrimary: 'Open admin & build',
  ctaSecondary: 'Browse examples',
  stats: {
    agents: 'AI agents',
    agentsValue: '12',
    pipeline: 'Pipeline stages',
    pipelineValue: '14',
    llm: 'LLM providers',
    llmValue: '4+',
    chains: 'Chains',
    chainsValue: '3',
  },
  featuresIntroGradientWord: 'Built',
  featuresIntroRest: 'for speed and substance',
  featuresIntroSubtitle:
    'Landings are the default guest deliverable; autonomous and admin-queued ideas often become full products — one pipeline, different delivery_profile, identical gates.',
  features: [
    {
      iconKey: 'sparkles',
      title: 'One phrase → presentable page',
      description:
        'Your sentence becomes the stakeholder brief through the same stages as autonomous builds — HTML/CSS/JS you preview in the sandbox; gates reject hollow stubs.',
      gradient: 'from-indigo-500 to-purple-500',
    },
    {
      iconKey: 'bot',
      title: 'Specialized agents',
      description:
        'Specialized roles per stage (Analyst, PM, Methodologist, Architect, Designer/UX, Developer, QA, Security, DevOps, Marketing, Sales, Evolution) — each step bounded so outputs stay maintainable. See `agents/` for the full list.',
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      iconKey: 'shield',
      title: 'Quality & security gates',
      description:
        'Demo checks, headless browser smoke, optional marketplace rules — rework loops until the product is show-ready.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      iconKey: 'rocket',
      title: 'Same runway as autonomous',
      description:
        'Research → spec → architecture → code → QA → security → DevOps → marketing → sales → evolution. Autonomous seeds ideas from the market; on-demand seeds from your phrase — no second-class pipeline.',
      gradient: 'from-orange-500 to-red-500',
    },
    {
      iconKey: 'chart',
      title: 'Director AI',
      description:
        'Meta-agent reviews pipeline health on a schedule and steers autonomous improvements.',
      gradient: 'from-cyan-500 to-blue-500',
    },
    {
      iconKey: 'coins',
      title: 'Crypto-ready storefront',
      description:
        'Affordable one-shot landing price (about $5 USDT when agents omit list pricing), multi-chain checkout — buyers pay on-chain, you ship files.',
      gradient: 'from-yellow-500 to-amber-500',
    },
  ],
  productsTitle: 'Marketplace examples',
  productsSubtitle:
    'Browse separately: brochure landings (hero generator) vs. full products (admin / autonomous pipeline). All listings passed quality gates.',
  productsLandingsTitle: 'Marketing landing pages',
  productsLandingsSubtitle:
    'Single-page brochure builds — same delivery path as the phrase box at the top of this page.',
  productsFullTitle: 'Full products',
  productsFullSubtitle:
    'Apps and services with real backends, data stores, and compose-friendly repos — queued from Admin or Director.',
  ctaBannerTitle: 'Ready to ship your next page or product?',
  ctaBannerSubtitle:
    'Self-host the factory, connect LLM keys, then use the phrase box for a landing or Admin for a full build — same agents, same quality bar.',
  ctaBannerPrimary: 'Open admin',
  ctaBannerSecondary: 'Documentation',
  footerTagline: 'AI-Factory v2.1',
  footerDocumentation: 'Documentation',
  footerBlog: 'Blog',
  footerLaunchKit: 'Launch Kit',
  footerBadge: 'Embeddable Badge',
  footerApiReference: 'API Reference',
  footerGithub: 'GitHub',
  footerAdminPanel: 'Admin Panel',
  pipelineSectionTitle: 'One pipeline, two front doors',
  pipelineSectionSubtitle:
    'Autonomous mode feeds market research and generated ideas; on-demand uses your phrase as the brief. Same agent path — spec, build, QA, and beyond.',
  pipelineDesignerEyebrow: 'Product experience',
  pipelineDesignerTitle: 'Designer layer — modern UI by default',
  pipelineDesignerBody:
    'Before code ships, the Architect emits a structured `ui_experience` brief: tokens, typography, motion, and a signature visual moment. The Developer treats it as binding for browser deliverables — so landings read as intentional product design, not generic AI gray boxes.',
  architectureEyebrow: 'Runtime topology',
  architectureTitle: 'Architecture at a glance',
  architectureSubtitle:
    'One control plane: web tier, background workers, routed models, and durable workspace — shown as a live orbit around the agent fleet.',
  architectureHubLabel: 'Agents',
  architectureHubRoles: 'PM · Architect · Dev · QA · Sec · Ops · Mkt · Sales · Evolution',
  architectureHubFooter: 'Single pipeline · shared gates',
  architectureNodes: [
    { label: 'Next.js', sub: 'Storefront' },
    { label: 'FastAPI', sub: 'Public & admin API' },
    { label: 'Pipeline worker', sub: 'Quality gates' },
    { label: 'Director AI', sub: 'Signals & reports' },
    { label: 'LLM router', sub: 'Multi-provider' },
    { label: 'Data plane', sub: 'SQLite · artifacts' },
  ],
};

export function detectMarketingLocale(): MarketingLocale {
  if (typeof window === 'undefined') {
    const env = (process.env.NEXT_PUBLIC_MARKETING_LOCALE || '').toLowerCase();
    if (env.startsWith('ru')) return 'ru';
    if (env.startsWith('es')) return 'es';
    return 'en';
  }
  const stored = window.localStorage.getItem('marketing_locale');
  if (stored === 'ru' || stored === 'es' || stored === 'en') return stored;
  const nav = navigator.language.toLowerCase();
  if (nav.startsWith('ru')) return 'ru';
  if (nav.startsWith('es')) return 'es';
  const env = (process.env.NEXT_PUBLIC_MARKETING_LOCALE || '').toLowerCase();
  if (env.startsWith('ru')) return 'ru';
  if (env.startsWith('es')) return 'es';
  return 'en';
}

export function saveMarketingLocale(locale: MarketingLocale): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem('marketing_locale', locale);
  window.dispatchEvent(new CustomEvent('marketing-locale-changed', { detail: locale }));
}

export function getMarketingStrings(locale?: string | null): MarketingStrings {
  const raw = (locale || '').toLowerCase();
  if (raw.startsWith('ru')) return MARKETING_RU;
  if (raw.startsWith('es')) return MARKETING_ES;
  return EN;
}
