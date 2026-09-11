'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Cpu, KeyRound, Loader2, Menu, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Sidebar } from '@/components/admin/AdminSidebar';
import { AdminShellOnboarding } from '@/components/admin/AdminShellOnboarding';
import { FactoryHoldBanner } from '@/components/admin/FactoryHoldBanner';
import { PipelineFocusBanner } from '@/components/admin/PipelineFocusBanner';
import {
  AgentLogsTabLazy,
  AgentsTabLazy,
  BlogPostsTabLazy,
  BrainstormingTabLazy,
  CorporateChatTabLazy,
  DashboardTabLazy,
  DirectorTabLazy,
  DiscoveryTabLazy,
  FactoryFloorTabLazy,
  FilesTabLazy,
  LLMLogsTabLazy,
  MonitorTabLazy,
  NewProductTabLazy,
  OutreachTabLazy,
  PipelineTabLazy,
  ProductShowcaseTabLazy,
  PromptImprovementTabLazy,
  ProvidersTabLazy,
  SandboxTabLazy,
  SecurityTabLazy,
  SettingsTabLazy,
  SetupWizardTabLazy,
  SupportQueueTabLazy,
  TimeTravelReplayTabLazy,
  UsersTabLazy,
  WorkshopTabLazy,
} from '@/lib/adminTabLoaders';
import { t } from '@/lib/adminI18n';
import api, { ApiRequestError } from '@/lib/api';
import { prefetchAdminDashboard } from '@/lib/prefetchAdminDashboard';
import { useAdminSessionStore } from '@/lib/adminSessionStore';

const ADMIN_TAB_IDS = new Set([
  'dashboard',
  'setup',
  'monitor',
  'factory-floor',
  'time-travel',
  'showcase',
  'blog',
  'prompt-loop',
  'pipeline',
  'new-product',
  'workshop',
  'files',
  'agents',
  'providers',
  'llm-logs',
  'agent-logs',
  'security',
  'sandbox',
  'director',
  'discovery',
  'settings',
  'chat',
  'brainstorming',
  'support-queue',
  'outreach',
  'users',
]);

export default function AdminPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-[#0a0a0f] text-gray-400">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
        </div>
      }
    >
      <AdminPageInner />
    </Suspense>
  );
}

function AdminPageInner() {
  const router = useRouter();
  const pathname = usePathname() || '/admin';
  const searchParams = useSearchParams();
  const activeTab = useMemo(() => {
    const tab = searchParams.get('tab');
    if (tab && ADMIN_TAB_IDS.has(tab)) return tab;
    return 'dashboard';
  }, [searchParams]);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ADMIN_TAB_IDS.has(tab)) return;
    router.replace('/admin?tab=dashboard', { scroll: false });
  }, [router, searchParams]);

  const changeTab = useCallback(
    (tab: string) => {
      if (!ADMIN_TAB_IDS.has(tab)) return;
      const next = new URLSearchParams();
      next.set('tab', tab);
      if (tab === 'pipeline') {
        const pipelineSearch = searchParams.get('pipelineSearch')?.trim();
        if (pipelineSearch) next.set('pipelineSearch', pipelineSearch);
      } else if (tab === 'llm-logs') {
        const llmAgent = searchParams.get('llmAgent')?.trim();
        if (llmAgent) next.set('llmAgent', llmAgent);
      } else if (tab === 'agent-logs') {
        const agentLog = searchParams.get('agentLog')?.trim();
        if (agentLog) next.set('agentLog', agentLog);
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* clear local session even if revoke fails */
    }
    localStorage.removeItem('admin_token');
    window.location.href = '/';
  }, []);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const locale = useAdminSessionStore((s) => s.locale);
  const setLocale = useAdminSessionStore((s) => s.setLocale);
  const hydrateLocale = useAdminSessionStore((s) => s.hydrateLocale);
  const refreshMe = useAdminSessionStore((s) => s.refreshMe);
  const adminRole = useAdminSessionStore((s) => s.me?.role ?? null);
  const sandboxDemoPasswordDefault = useAdminSessionStore(
    (s) => Boolean(s.me?.sandbox_demo_password_uses_default),
  );
  const [sessionVerifying, setSessionVerifying] = useState(true);
  const [demoPwBannerDismissed, setDemoPwBannerDismissed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('aicom_hide_default_demo_pw_banner') === '1';
  });
  const [factoryOnHold, setFactoryOnHold] = useState(false);
  const [focusProductId, setFocusProductId] = useState<string | null>(null);
  const [focusPausedCount, setFocusPausedCount] = useState(0);

  const redirectToLogin = useCallback(() => {
    localStorage.removeItem('admin_token');
    window.location.replace('/admin/login');
  }, []);

  const loadAdminChrome = useCallback(async () => {
    prefetchAdminDashboard();
    try {
      const s = await api.getAdminSettings();
      setFactoryOnHold(Boolean(s.factory_on_hold));
      const fid = s.factory_focus_product_id;
      setFocusProductId(typeof fid === 'string' && fid.trim() ? fid.trim() : null);
    } catch {
      setFactoryOnHold(false);
      setFocusProductId(null);
    }
    try {
      const fm = await api.getPipelineFocusMode();
      setFocusProductId(fm.focus_product_id);
      setFocusPausedCount(Number(fm.paused_count) || 0);
    } catch {
      /* settings may already carry focus id */
    }
  }, []);

  useEffect(() => {
    hydrateLocale();

    let cancelled = false;
    const authMeTimeoutMs = 12_000;

    const verifySession = async () => {
      setSessionVerifying(true);
      try {
        await api.getMe({ clientTimeoutMs: authMeTimeoutMs });
        if (cancelled) return;
        await refreshMe();
        await loadAdminChrome();
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiRequestError && (err.status === 401 || err.status === 403)) {
          redirectToLogin();
          return;
        }
        /* Slow backend — keep shell usable; settings hydrate on tab focus. */
        void loadAdminChrome();
      } finally {
        if (!cancelled) setSessionVerifying(false);
      }
    };

    void verifySession();

    return () => {
      cancelled = true;
    };
  }, [hydrateLocale, loadAdminChrome, redirectToLogin, refreshMe]);

  useEffect(() => {
    void loadAdminChrome();
  }, [activeTab, loadAdminChrome]);

  useEffect(() => {
    const onHoldChange = (e: Event) => {
      const detail = (e as CustomEvent<boolean>).detail;
      if (typeof detail === 'boolean') setFactoryOnHold(detail);
    };
    window.addEventListener('aicom-factory-hold', onHoldChange);
    return () => window.removeEventListener('aicom-factory-hold', onHoldChange);
  }, []);

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTabLazy locale={locale} />;
      case 'setup':
        return <SetupWizardTabLazy adminRole={adminRole} locale={locale} />;
      case 'monitor':
        return <MonitorTabLazy locale={locale} />;
      case 'factory-floor':
        return <FactoryFloorTabLazy locale={locale} />;
      case 'time-travel':
        return <TimeTravelReplayTabLazy locale={locale} />;
      case 'showcase':
        return <ProductShowcaseTabLazy locale={locale} />;
      case 'blog':
        return <BlogPostsTabLazy locale={locale} />;
      case 'prompt-loop':
        return <PromptImprovementTabLazy locale={locale} />;
      case 'products':
        return <PipelineTabLazy locale={locale} />;
      case 'new-product':
        return <NewProductTabLazy locale={locale} />;
      case 'workshop':
        return <WorkshopTabLazy locale={locale} />;
      case 'pipeline':
        return <PipelineTabLazy locale={locale} />;
      case 'agents':
        return <AgentsTabLazy locale={locale} />;
      case 'providers':
        return <ProvidersTabLazy key={locale} locale={locale} />;
      case 'llm-logs':
        return <LLMLogsTabLazy locale={locale} />;
      case 'agent-logs':
        return <AgentLogsTabLazy locale={locale} />;
      case 'security':
        return <SecurityTabLazy locale={locale} />;
      case 'files':
        return <FilesTabLazy locale={locale} />;
      case 'sandbox':
        return <SandboxTabLazy locale={locale} />;
      case 'director':
        return <DirectorTabLazy locale={locale} />;
      case 'discovery':
        return <DiscoveryTabLazy locale={locale} />;
      case 'settings':
        return <SettingsTabLazy locale={locale} />;
      case 'users':
        if (adminRole !== 'super_admin') {
          return <DashboardTabLazy locale={locale} />;
        }
        return <UsersTabLazy locale={locale} />;
      case 'chat':
        return <CorporateChatTabLazy locale={locale} />;
      case 'brainstorming':
        return <BrainstormingTabLazy locale={locale} />;
      case 'support-queue':
        return <SupportQueueTabLazy locale={locale} />;
      case 'outreach':
        return <OutreachTabLazy locale={locale} />;
      default:
        return <DashboardTabLazy locale={locale} />;
    }
  };

  return (
    <div className="flex h-[100dvh] max-h-[100dvh] min-w-0 overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onTabChange={changeTab}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        locale={locale}
        onLocaleChange={setLocale}
        onLogout={handleLogout}
        showUsersTab={adminRole === 'super_admin'}
      />

      <main className="flex-1 min-h-0 min-w-0 px-4 md:px-8 overflow-x-auto overflow-y-auto overscroll-contain pt-[max(1rem,env(safe-area-inset-top))] md:pt-8 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-between mb-6 md:hidden">
          <button
            onClick={() => setSidebarCollapsed(false)}
            className="p-2 rounded-lg hover:bg-white/5 transition-colors"
          >
            <Menu className="w-6 h-6 text-gray-400" />
          </button>
          <Link
            href="/"
            className="rounded-lg p-1 transition-colors hover:bg-white/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
            aria-label={t(locale, 'app.backToSite')}
            title={t(locale, 'app.backToSite')}
          >
            <Cpu className="h-6 w-6 text-indigo-400" aria-hidden />
          </Link>
        </div>

        {sessionVerifying ? (
          <p className="mb-4 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" aria-hidden />
            {t(locale, 'app.authChecking')}
          </p>
        ) : null}

        {sandboxDemoPasswordDefault && !demoPwBannerDismissed ? (
          <GlassCard className="mb-6 border border-amber-500/35 bg-amber-950/25 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 gap-3">
                <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" aria-hidden />
                <div className="min-w-0 space-y-1">
                  <h3 className="text-sm font-semibold text-amber-100">
                    {t(locale, 'security.demoPassword.title')}
                  </h3>
                  <p className="text-xs leading-relaxed text-amber-100/85">
                    {t(locale, 'security.demoPassword.body')}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
                <button
                  type="button"
                  className="rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-50 hover:bg-amber-500/25"
                  onClick={() => changeTab('sandbox')}
                >
                  {t(locale, 'security.demoPassword.openSandbox')}
                </button>
                <button
                  type="button"
                  className="rounded-lg p-1.5 text-amber-200/80 hover:bg-white/10 hover:text-white"
                  aria-label={t(locale, 'security.demoPassword.dismiss')}
                  title={t(locale, 'security.demoPassword.dismiss')}
                  onClick={() => {
                    sessionStorage.setItem('aicom_hide_default_demo_pw_banner', '1');
                    setDemoPwBannerDismissed(true);
                  }}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          </GlassCard>
        ) : null}

        <AdminShellOnboarding activeTab={activeTab} locale={locale} />

        {factoryOnHold && activeTab !== 'settings' ? (
          <FactoryHoldBanner
            locale={locale}
            onOpenSettings={() => {
              window.location.hash = 'factory-hold';
              changeTab('settings');
            }}
          />
        ) : null}

        {focusProductId && activeTab !== 'pipeline' && activeTab !== 'products' ? (
          <PipelineFocusBanner
            locale={locale}
            focusProductId={focusProductId}
            pausedCount={focusPausedCount}
            onOpenPipeline={() => changeTab('pipeline')}
          />
        ) : null}

        {renderTab()}
      </main>
    </div>
  );
}
