'use client';

import React, { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Cpu,
  BookOpen,
  ChevronRight,
  Menu,
  X,
  Home,
  Settings,
  Globe,
  ArrowLeft,
  Copy,
  Check,
  FileText,
  Shield,
} from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { buildDocSections, type DocSection, type DocsSectionUi } from '@/lib/docs-sections';
import {
  detectDocLocale,
  getDocsStrings,
  saveDocLocale,
  type DocLocale,
  type DocsStrings,
} from '@/lib/docs-i18n';

function DocNavbar({
  locale,
  onLocaleChange,
  t,
}: {
  locale: DocLocale;
  onLocaleChange: (l: DocLocale) => void;
  t: DocsStrings;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const locales: DocLocale[] = ['en', 'ru', 'es', 'fr', 'zh'];

  const switchLocale = (l: DocLocale) => {
    onLocaleChange(l);
    setLangOpen(false);
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group">
          <Cpu className="w-6 h-6 text-indigo-400 group-hover:text-indigo-300 transition-colors" />
          <span className="text-lg font-bold text-white">AI-Factory</span>
        </Link>
        <div className="hidden md:flex items-center gap-6">
          <Link href="/" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
            <Home className="w-4 h-4" />
            {t.nav.home}
          </Link>
          <a href="/docs" className="flex items-center gap-1.5 text-sm text-white transition-colors">
            <BookOpen className="w-4 h-4" />
            {t.nav.docs}
          </a>
          <a href="/admin" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
            <Settings className="w-4 h-4" />
            {t.nav.admin}
          </a>
          <div className="relative">
            <button
              type="button"
              onClick={() => setLangOpen(!langOpen)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-white/5 hover:bg-white/10 text-gray-300 transition-colors"
            >
              <Globe className="w-3.5 h-3.5" />
              {t.localeLabels[locale]}
            </button>
            {langOpen && (
              <div className="absolute right-0 top-full mt-1 py-1 rounded-lg bg-gray-900 border border-white/10 shadow-xl z-50 min-w-[130px]">
                {locales.map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => switchLocale(l)}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                      l === locale ? 'text-indigo-400 bg-indigo-500/10' : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {t.localeNames[l]}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden text-gray-400 hover:text-white transition-colors"
          aria-label={t.nav.toggle}
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
            <Link
              href="/"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white py-2 transition-colors"
            >
              <Home className="w-4 h-4" />
              {t.nav.home}
            </Link>
            <a
              href="/docs"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 text-sm text-white py-2 transition-colors"
            >
              <BookOpen className="w-4 h-4" />
              {t.nav.docs}
            </a>
            <a
              href="/admin"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white py-2 transition-colors"
            >
              <Settings className="w-4 h-4" />
              {t.nav.admin}
            </a>
            <div className="flex gap-2 pt-2 border-t border-white/5">
              {locales.map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => switchLocale(l)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    l === locale ? 'bg-indigo-500/20 text-indigo-400' : 'bg-white/5 text-gray-400 hover:text-white'
                  }`}
                >
                  {t.localeNames[l]}
                </button>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </nav>
  );
}

function DocSidebar({
  sections,
  activeSection,
  onSectionChange,
}: {
  sections: DocSection[];
  activeSection: string;
  onSectionChange: (id: string) => void;
}) {
  return (
    <aside className="w-64 flex-shrink-0 hidden lg:block">
      <nav className="sticky top-20 space-y-1">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <button
              key={section.id}
              type="button"
              onClick={() => onSectionChange(section.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                activeSection === section.id
                  ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{section.title}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function CodeBlock({
  code,
  language = 'bash',
  copyLabel,
}: {
  code: string;
  language?: string;
  copyLabel: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-4">
      <div className="absolute top-3 right-3 z-10">
        <button
          type="button"
          onClick={handleCopy}
          className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
          aria-label={copyLabel}
        >
          {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <div className="text-xs text-gray-500 px-4 pt-2 pb-1">{language}</div>
      <pre className="bg-black/40 border border-white/5 rounded-xl p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function InfoBox({
  title,
  children,
  variant = 'info',
}: {
  title: string;
  children: React.ReactNode;
  variant?: 'info' | 'warning' | 'success';
}) {
  const colors = {
    info: 'border-indigo-500/30 bg-indigo-500/5',
    warning: 'border-amber-500/30 bg-amber-500/5',
    success: 'border-emerald-500/30 bg-emerald-500/5',
  };
  const icons = {
    info: FileText,
    warning: Shield,
    success: Check,
  };
  const Icon = icons[variant];

  return (
    <div className={`flex gap-3 p-4 rounded-xl border ${colors[variant]} my-4`}>
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5 text-indigo-400" />
      <div>
        <p className="text-sm font-medium text-white mb-1">{title}</p>
        <div className="text-sm text-gray-400">{children}</div>
      </div>
    </div>
  );
}

function DocScreenshot({
  src,
  caption,
  ui,
}: {
  src: string;
  caption: string;
  ui: DocsStrings['ui'];
}) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="my-6">
      <div className="rounded-xl border border-white/10 overflow-hidden bg-gradient-to-br from-slate-900/90 to-indigo-950/50 shadow-lg shadow-indigo-500/5">
        {!failed ? (
          // eslint-disable-next-line @next/next/no-img-element -- static docs assets in /public/docs-screenshots
          <img src={src} alt="" className="w-full block" onError={() => setFailed(true)} />
        ) : (
          <div className="p-10 text-center text-sm text-gray-400 space-y-2">
            <p className="text-gray-300 font-medium">{ui.screenshotNotBundled}</p>
            <p>
              {ui.screenshotHintPrefix}{' '}
              <code className="text-cyan-400/90">web/frontend</code> {ui.screenshotHintRun}{' '}
              <code className="text-cyan-400/90">npm run capture-docs-screenshots</code>
              {ui.screenshotHintMiddle}
              <code className="text-cyan-400/90">{ui.screenshotHintEnv}</code>
              {ui.screenshotHintAnd}
              <code className="text-cyan-400/90">{ui.screenshotHintPassword}</code>.
            </p>
          </div>
        )}
      </div>
      <figcaption className="text-xs text-gray-500 mt-2 tracking-wide">{caption}</figcaption>
    </figure>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xl font-semibold text-white mt-8 mb-3">{children}</h3>;
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return <p className="text-gray-400 leading-relaxed mb-3">{children}</p>;
}

function List({ items }: { items: React.ReactNode[] }): React.ReactElement {
  return (
    <ul className="space-y-2 my-3">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-gray-400">
          <ChevronRight className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default function DocsPage() {
  const [locale, setLocale] = useState<DocLocale>(() => detectDocLocale());
  const [activeSection, setActiveSection] = useState('overview');
  const t = useMemo(() => getDocsStrings(locale), [locale]);

  const onLocaleChange = useCallback((l: DocLocale) => {
    setLocale(l);
    saveDocLocale(l);
  }, []);

  const sectionUi: DocsSectionUi = useMemo(() => {
    const uiStrings = t.ui;
    return {
      CodeBlock: ({ code, language }) => (
        <CodeBlock code={code} language={language} copyLabel={uiStrings.copyCode} />
      ),
      InfoBox,
      DocScreenshot: ({ src, caption }) => (
        <DocScreenshot src={src} caption={caption} ui={uiStrings} />
      ),
      SubHeading,
      Paragraph,
      List,
    };
  }, [t]);

  const docSections = useMemo(() => buildDocSections(t, sectionUi), [t, sectionUi]);
  const currentDoc = docSections.find((s) => s.id === activeSection) || docSections[0];
  const currentIndex = docSections.findIndex((s) => s.id === activeSection);

  return (
    <div className="min-h-screen">
      <DocNavbar locale={locale} onLocaleChange={onLocaleChange} t={t} />

      <section className="relative pt-20 pb-12 px-4">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 left-1/3 w-64 h-64 bg-indigo-500/10 rounded-full blur-[100px]" />
        </div>
        <div className="relative max-w-7xl mx-auto">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            {t.hero.backToHome}
          </Link>
          <div className="flex items-center gap-3 mb-2">
            <BookOpen className="w-8 h-8 text-indigo-400" />
            <h1 className="text-4xl md:text-5xl font-bold">
              <span className="text-gradient">{t.hero.title}</span>
            </h1>
          </div>
          <p className="text-gray-400 text-lg max-w-2xl">{t.hero.subtitle}</p>
        </div>
      </section>

      <section className="pb-24 px-4">
        <div className="mx-auto flex max-w-7xl min-w-0 flex-col gap-8 lg:flex-row">
          <DocSidebar
            sections={docSections}
            activeSection={activeSection}
            onSectionChange={setActiveSection}
          />

          <div className="w-full shrink-0 lg:hidden">
            <select
              value={activeSection}
              onChange={(e) => setActiveSection(e.target.value)}
              className="w-full glass-card p-3 text-white bg-transparent border border-white/10 rounded-xl text-sm"
            >
              {docSections.map((section) => (
                <option key={section.id} value={section.id} className="bg-gray-900">
                  {section.title}
                </option>
              ))}
            </select>
          </div>

          <motion.div
            key={activeSection}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="min-w-0 w-full flex-1"
          >
            <div className="max-w-4xl">{currentDoc.content}</div>

            <div className="flex items-center justify-between mt-12 pt-8 border-t border-white/5">
              <div>
                {currentIndex > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSection(docSections[currentIndex - 1].id);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    {docSections[currentIndex - 1]?.title}
                  </button>
                )}
              </div>
              <div>
                {currentIndex < docSections.length - 1 && (
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSection(docSections[currentIndex + 1].id);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    {docSections[currentIndex + 1]?.title}
                    <ChevronRight className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-white/5 px-4 pt-8 pb-[var(--storefront-footer-pad)] md:py-8">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <span className="text-sm text-gray-400">{t.footer.tagline}</span>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
            <Link href="/" className="hover:text-gray-300 transition-colors">
              {t.footer.home}
            </Link>
            <a href="/admin" className="hover:text-gray-300 transition-colors">
              {t.footer.admin}
            </a>
            <a href="/api/docs" className="hover:text-gray-300 transition-colors">
              {t.footer.apiDocs}
            </a>
            <a
              href="https://github.com/alexar76/aicom"
              className="hover:text-gray-300 transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t.footer.github}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
