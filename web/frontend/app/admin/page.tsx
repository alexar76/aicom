'use client';

import dynamic from 'next/dynamic';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Cpu, KeyRound, Loader2, Menu, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import BrainstormingTab from '@/components/BrainstormingTab';
import SupportQueueTab from '@/components/SupportQueueTab';
import OutreachTab from '@/components/OutreachTab';
import { Sidebar } from '@/components/admin/AdminSidebar';
import { AdminShellOnboarding } from '@/components/admin/AdminShellOnboarding';
import { FactoryHoldBanner } from '@/components/admin/FactoryHoldBanner';
import {
  AgentsTab,
  AgentLogsTab,
  CorporateChatTab,
  DashboardTab,
  DirectorTab,
  DiscoveryTab,
  LLMLogsTab,
  MonitorTab,
  FactoryFloorTab,
  TimeTravelReplayTab,
  ProductShowcaseTab,
  BlogPostsTab,
  PromptImprovementTab,
  NewProductTab,
  PipelineTab,
  ProvidersTab,
  SandboxTab,
  SecurityTab,
  SettingsTab,
  SetupWizardTab,
  UsersTab,
  WorkshopTab,
} from '@/components/admin/AdminTabs';

const FilesTabLazy = dynamic(
  () => import('@/components/admin/tabs/FilesTab').then((m) => ({ default: m.FilesTab })),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-gray-400">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
        <p className="text-sm">Loading Files…</p>
      </div>
    ),
  },
);
import { t } from '@/lib/adminI18n';
import api from '@/lib/api';
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

  const changeTab = useCallback(
    (tab: string) => {
      if (!ADMIN_TAB_IDS.has(tab)) return;
      const next = new URLSearchParams(searchParams.toString());
      next.set('tab', tab);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
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
  const authChecked = useAdminSessionStore((s) => s.authChecked);
  const setAuthChecked = useAdminSessionStore((s) => s.setAuthChecked);
  const hydrateLocale = useAdminSessionStore((s) => s.hydrateLocale);
  const refreshMe = useAdminSessionStore((s) => s.refreshMe);
  const adminRole = useAdminSessionStore((s) => s.me?.role ?? null);
  const sandboxDemoPasswordDefault = useAdminSessionStore(
    (s) => Boolean(s.me?.sandbox_demo_password_uses_default),
  );
  const [demoPwBannerDismissed, setDemoPwBannerDismissed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('aicom_hide_default_demo_pw_banner') === '1';
  });
  const [factoryOnHold, setFactoryOnHold] = useState(false);

  useEffect(() => {
    hydrateLocale();
    api
      .getMe()
      .then(async () => {
        setAuthChecked(true);
        await refreshMe();
        prefetchAdminDashboard();
        try {
          const s = await api.getAdminSettings();
          setFactoryOnHold(Boolean(s.factory_on_hold));
        } catch {
          setFactoryOnHold(false);
        }
      })
      .catch(() => {
        localStorage.removeItem('admin_token');
        window.location.href = '/admin/login';
      });
  }, [hydrateLocale, refreshMe, setAuthChecked]);

  useEffect(() => {
    if (!authChecked) return;
    void api.getAdminSettings().then((s) => setFactoryOnHold(Boolean(s.factory_on_hold))).catch(() => {});
  }, [authChecked, activeTab]);

  useEffect(() => {
    if (!authChecked) return;
    const onHoldChange = (e: Event) => {
      const detail = (e as CustomEvent<boolean>).detail;
      if (typeof detail === 'boolean') setFactoryOnHold(detail);
    };
    window.addEventListener('aicom-factory-hold', onHoldChange);
    return () => window.removeEventListener('aicom-factory-hold', onHoldChange);
  }, [authChecked]);

  const renderTab = () => {
    if (!authChecked) return null;
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab locale={locale} />;
      case 'setup':
        return <SetupWizardTab adminRole={adminRole} locale={locale} />;
      case 'monitor':
        return <MonitorTab locale={locale} />;
      case 'factory-floor':
        return <FactoryFloorTab locale={locale} />;
      case 'time-travel':
        return <TimeTravelReplayTab locale={locale} />;
      case 'showcase':
        return <ProductShowcaseTab locale={locale} />;
      case 'blog':
        return <BlogPostsTab locale={locale} />;
      case 'prompt-loop':
        return <PromptImprovementTab locale={locale} />;
      case 'products':
        return <PipelineTab locale={locale} />;
      case 'new-product':
        return <NewProductTab locale={locale} />;
      case 'workshop':
        return <WorkshopTab locale={locale} />;
      case 'pipeline':
        return <PipelineTab locale={locale} />;
      case 'agents':
        return <AgentsTab locale={locale} />;
      case 'providers':
        return <ProvidersTab locale={locale} />;
      case 'llm-logs':
        return <LLMLogsTab locale={locale} />;
      case 'agent-logs':
        return <AgentLogsTab locale={locale} />;
      case 'security':
        return <SecurityTab locale={locale} />;
      case 'files':
        return <FilesTabLazy locale={locale} />;
      case 'sandbox':
        return <SandboxTab locale={locale} />;
      case 'director':
        return <DirectorTab locale={locale} />;
      case 'discovery':
        return <DiscoveryTab locale={locale} />;
      case 'settings':
        return <SettingsTab locale={locale} />;
      case 'users':
        if (adminRole !== 'super_admin') {
          return <DashboardTab locale={locale} />;
        }
        return <UsersTab locale={locale} />;
      case 'chat':
        return <CorporateChatTab locale={locale} />;
      case 'brainstorming':
        return <BrainstormingTab locale={locale} />;
      case 'support-queue':
        return <SupportQueueTab locale={locale} />;
      case 'outreach':
        return <OutreachTab locale={locale} />;
      default:
        return <DashboardTab locale={locale} />;
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

        {authChecked &&
          sandboxDemoPasswordDefault &&
          !demoPwBannerDismissed && (
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
          )}

        {authChecked ? <AdminShellOnboarding activeTab={activeTab} locale={locale} /> : null}

        {authChecked && factoryOnHold && activeTab !== 'settings' ? (
          <FactoryHoldBanner
            locale={locale}
            onOpenSettings={() => {
              window.location.hash = 'factory-hold';
              changeTab('settings');
            }}
          />
        ) : null}

        {renderTab()}
      </main>
    </div>
  );
}
