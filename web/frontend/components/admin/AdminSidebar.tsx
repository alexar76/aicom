'use client';

import Link from 'next/link';
import {
  LayoutDashboard,
  Cpu,
  Radio,
  Activity,
  Plus,
  FileText,
  Bot,
  Shield,
  ScrollText,
  List,
  BarChart3,
  Settings,
  Star,
  MessageCircle,
  Terminal,
  BrainCircuit,
  Inbox,
  Megaphone,
  UserCog,
  LogOut,
  X,
  LayoutGrid,
  Rocket,
  Languages,
  ChevronLeft,
  ChevronRight,
  Zap,
  Clock,
  Film,
  Sparkles,
  Newspaper,
} from 'lucide-react';
import { AdminLocale, t } from '@/lib/adminI18n';

// ── Sidebar ──────────────────────────────────────────────────────────────

export function Sidebar({
  activeTab,
  collapsed,
  onToggle,
  locale,
  onLocaleChange,
  onLogout,
  showUsersTab,
}: {
  activeTab: string;
  onTabChange?: (tab: string) => void;
  collapsed: boolean;
  onToggle: () => void;
  locale: AdminLocale;
  onLocaleChange: (locale: AdminLocale) => void;
  onLogout: () => void;
  /** Super-admin only: manage admin accounts */
  showUsersTab?: boolean;
}) {
  const tabs = [
    { id: 'dashboard', label: t(locale, 'tab.dashboard'), icon: LayoutDashboard },
    { id: 'setup', label: t(locale, 'tab.setup'), icon: Rocket },
    { id: 'monitor', label: t(locale, 'tab.monitor'), icon: Radio },
    { id: 'factory-floor', label: t(locale, 'tab.factoryFloor'), icon: Zap },
    { id: 'time-travel', label: t(locale, 'tab.timeTravel'), icon: Clock },
    { id: 'showcase', label: t(locale, 'tab.showcase'), icon: Film },
    { id: 'blog', label: t(locale, 'tab.blog'), icon: Newspaper },
    { id: 'prompt-loop', label: t(locale, 'tab.promptLoop'), icon: Sparkles },
    { id: 'pipeline', label: t(locale, 'tab.pipeline'), icon: Activity },
    { id: 'new-product', label: t(locale, 'tab.newProduct'), icon: Plus },
    { id: 'workshop', label: t(locale, 'tab.workshop'), icon: LayoutGrid },
    { id: 'files', label: t(locale, 'tab.files'), icon: FileText },
    { id: 'agents', label: t(locale, 'tab.agents'), icon: Bot },
    { id: 'providers', label: t(locale, 'tab.providers'), icon: Cpu },
    { id: 'llm-logs', label: t(locale, 'tab.llmLogs'), icon: ScrollText },
    { id: 'agent-logs', label: t(locale, 'tab.agentLogs'), icon: List },
    { id: 'security', label: t(locale, 'tab.security'), icon: Shield },
    { id: 'sandbox', label: t(locale, 'tab.sandbox'), icon: Terminal },
    { id: 'director', label: t(locale, 'tab.director'), icon: BarChart3 },
    { id: 'discovery', label: t(locale, 'tab.discovery'), icon: Star },
    { id: 'settings', label: t(locale, 'tab.settings'), icon: Settings },
    ...(showUsersTab
      ? [{ id: 'users', label: t(locale, 'tab.users'), icon: UserCog }]
      : []),
    { id: 'chat', label: t(locale, 'tab.chat'), icon: MessageCircle },
    { id: 'brainstorming', label: t(locale, 'tab.brainstorming'), icon: BrainCircuit },
    { id: 'support-queue', label: t(locale, 'tab.supportQueue'), icon: Inbox },
    { id: 'outreach', label: t(locale, 'tab.outreach'), icon: Megaphone },
  ];

  return (
    <>
      {/* Mobile overlay */}
      {!collapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={`fixed md:sticky top-0 left-0 h-[100dvh] max-h-[100dvh] z-50 bg-[#0b1120] border-r border-white/10 shadow-[4px_0_24px_rgba(0,0,0,0.45)] transition-all duration-300 flex flex-col min-h-0 ${
          collapsed ? '-translate-x-full md:translate-x-0 md:w-20' : 'w-64'
        }`}
      >
        <div
          className={`shrink-0 border-b border-white/10 bg-[#0b1120] ${
            collapsed ? 'p-3 flex flex-col items-center gap-2' : 'p-4 flex items-center justify-between gap-2'
          }`}
        >
          <Link
            href="/"
            className={`flex min-w-0 items-center rounded-lg p-1 -m-1 transition-colors hover:bg-white/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40 ${
              collapsed ? 'justify-center' : 'gap-3'
            }`}
            title={t(locale, 'app.backToSite')}
            aria-label={t(locale, 'app.backToSite')}
          >
            <Cpu className="h-6 w-6 shrink-0 text-indigo-400" aria-hidden />
            {!collapsed && (
              <span className="font-semibold text-white truncate">{t(locale, 'app.adminPanel')}</span>
            )}
          </Link>
          <button
            type="button"
            onClick={onToggle}
            className="hidden md:flex p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-white"
            aria-label={collapsed ? t(locale, 'sidebar.expandMenu') : t(locale, 'sidebar.collapseMenu')}
            title={collapsed ? t(locale, 'sidebar.expandMenu') : t(locale, 'sidebar.collapseMenu')}
          >
            {collapsed ? (
              <ChevronRight className="w-5 h-5 shrink-0" aria-hidden />
            ) : (
              <ChevronLeft className="w-5 h-5 shrink-0" aria-hidden />
            )}
          </button>
          <button
            type="button"
            onClick={onToggle}
            className="p-1 rounded-lg hover:bg-white/10 transition-colors md:hidden"
            aria-label={t(locale, 'sidebar.collapseMenu')}
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto overscroll-contain bg-[#0b1120] p-3 space-y-1">
          {tabs.map((tab) => (
            <Link
              key={tab.id}
              href={`/admin?tab=${tab.id}`}
              scroll={false}
              onClick={() => {
                if (window.innerWidth < 768) onToggle();
              }}
              className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                activeTab === tab.id
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <tab.icon className="w-5 h-5 shrink-0 mt-0.5" />
              {!collapsed && (
                <span className="min-w-0 flex-1 text-left leading-snug">{tab.label}</span>
              )}
            </Link>
          ))}
        </nav>

        <div className="shrink-0 mt-auto border-t border-white/10 left-0 right-0 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] space-y-2 bg-[#0b1120]">
          <div className={collapsed ? 'flex flex-col items-center gap-1.5' : 'px-3'}>
            {!collapsed && (
              <span className="text-[11px] text-gray-500 uppercase tracking-wide block mb-1">
                {t(locale, 'app.language')}
              </span>
            )}
            {collapsed && <Languages className="w-4 h-4 text-gray-500 shrink-0" aria-hidden />}
            <select
              value={locale}
              onChange={(e) => onLocaleChange(e.target.value as AdminLocale)}
              aria-label={t(locale, 'app.language')}
              title={t(locale, 'app.language')}
              className={
                collapsed
                  ? 'w-14 bg-white/5 border border-white/10 rounded-lg px-1 py-1.5 text-[11px] text-white text-center'
                  : 'w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-sm text-white'
              }
            >
              {collapsed ? (
                <>
                  <option value="en">EN</option>
                  <option value="ru">RU</option>
                  <option value="es">ES</option>
                </>
              ) : (
                <>
                  <option value="en">English</option>
                  <option value="ru">Russian</option>
                  <option value="es">Español</option>
                </>
              )}
            </select>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="w-full flex items-start justify-center md:justify-start gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all"
            aria-label={t(locale, 'app.logout')}
          >
            <LogOut className="w-5 h-5 shrink-0 mt-0.5" strokeWidth={2} />
            {!collapsed && (
              <span className="min-w-0 flex-1 text-left leading-snug">{t(locale, 'app.logout')}</span>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
