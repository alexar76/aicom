'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Bot,
  ChevronDown,
  Cpu,
  Home,
  Info,
  Layers,
  Menu,
  Package,
  Rocket,
  ScrollText,
  Settings,
  Sparkles,
  Star,
  Tag,
  TrendingUp,
  X,
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
  detectMarketingLocale,
  getMarketingStrings,
  saveMarketingLocale,
  type MarketingLocale,
} from '@/lib/marketing';

export function PublicMarketingNav({ activePath }: { activePath?: string }) {
  const [locale, setLocale] = useState<MarketingLocale>('en');
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreWrapRef = useRef<HTMLDivElement>(null);
  const copy = getMarketingStrings(locale);

  useEffect(() => {
    setLocale(detectMarketingLocale());
    const sync = () => setLocale(detectMarketingLocale());
    window.addEventListener('marketing-locale-changed', sync);
    return () => window.removeEventListener('marketing-locale-changed', sync);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const onLocaleChange = (code: MarketingLocale) => {
    saveMarketingLocale(code);
    setLocale(code);
  };

  useEffect(() => {
    if (!moreOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (moreWrapRef.current && !moreWrapRef.current.contains(e.target as Node)) setMoreOpen(false);
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

  const navLinksPrimary = [
    { label: copy.navGenerateLanding, href: '/#hero-generate', icon: Sparkles },
    { label: copy.navExplore, href: '/explore', icon: Layers },
    { label: copy.navProducts, href: '/#products', icon: Bot },
    { label: copy.navDocs, href: '/docs', icon: BookOpen },
    { label: copy.navAdmin, href: '/admin', icon: Settings },
  ];

  const navLinksMore = [
    { label: copy.navHome, href: '/', icon: Home },
    { label: copy.navFactoryIq, href: '/iq', icon: TrendingUp },
    { label: copy.navFeatures, href: '/#features', icon: Star },
    { label: copy.navAbout, href: '/about', icon: Info },
    { label: copy.navUpdates, href: '/updates', icon: ScrollText },
    { label: copy.navBlog, href: '/blog', icon: BookOpen },
    { label: copy.navLaunchKit, href: '/launch-kit', icon: Rocket },
    { label: copy.navBadge, href: '/badge', icon: Tag },
    { label: copy.navIdea, href: '/lead', icon: Package },
    { label: copy.navBenchmark, href: '/benchmark', icon: BarChart3 },
  ];

  const isActive = (href: string) => {
    if (!activePath) return false;
    if (href === '/') return activePath === '/';
    return activePath === href || activePath.startsWith(href + '/');
  };

  return (
    <nav className="fixed top-0 inset-x-0 z-50 glass border-b border-white/5 bg-black/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2 min-w-0">
        <Link href="/" className="flex items-center gap-2 group min-w-0 shrink-0 max-w-[calc(100%-3.5rem)]">
          <Cpu className="w-6 h-6 text-indigo-400 group-hover:text-indigo-300 transition-colors shrink-0" />
          <span className="text-lg font-bold text-white truncate">{copy.brandName}</span>
        </Link>

        <div className="hidden md:flex items-center gap-3 lg:gap-4 whitespace-nowrap">
          {navLinksPrimary.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-1.5 text-sm transition-colors shrink-0 whitespace-nowrap ${
                isActive(link.href) ? 'text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <link.icon className="w-4 h-4 shrink-0" />
              <span>{link.label}</span>
            </Link>
          ))}
          <div className="relative shrink-0" ref={moreWrapRef}>
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors py-1 whitespace-nowrap"
            >
              <span>{copy.navMore}</span>
              <ChevronDown className={`w-4 h-4 transition-transform ${moreOpen ? 'rotate-180' : ''}`} />
            </button>
            {moreOpen && (
              <div className="absolute right-0 mt-2 min-w-[13rem] rounded-xl border border-white/10 bg-black/95 backdrop-blur-xl py-2 shadow-xl z-[60]">
                {navLinksMore.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMoreOpen(false)}
                    className={`flex items-center gap-2 px-3 py-2 text-sm transition-colors whitespace-nowrap ${
                      isActive(link.href)
                        ? 'bg-indigo-500/20 text-white'
                        : 'text-gray-300 hover:bg-white/10 hover:text-white'
                    }`}
                  >
                    <link.icon className="w-4 h-4 shrink-0 opacity-80" />
                    {link.label}
                  </Link>
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

        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden text-gray-400 hover:text-white transition-colors shrink-0 p-1 -mr-1"
          aria-label="Toggle menu"
        >
          {menuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {menuOpen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:hidden border-t border-white/5 bg-black/90 backdrop-blur-xl"
        >
          <div className="px-4 py-3 space-y-2">
            {[...navLinksPrimary, ...navLinksMore].map((link) => (
              <Link
                key={link.href + link.label}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 text-sm text-gray-300 hover:text-white py-2"
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </Link>
            ))}
          </div>
        </motion.div>
      )}
    </nav>
  );
}
