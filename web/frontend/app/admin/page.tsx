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
import {
  AgentsTab,
  AgentLogsTab,
  CorporateChatTab,
  DashboardTab,
  DirectorTab,
  DiscoveryTab,
  LLMLogsTab,
  MonitorTab,
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
import { AdminLocale, detectAdminLocale, saveAdminLocale, t } from '@/lib/adminI18n';
import api from '@/lib/api';
import { prefetchAdminDashboard } from '@/lib/prefetchAdminDashboard';

const ADMIN_TAB_IDS = new Set([
  'dashboard',
  'setup',
  'monitor',
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

  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [authChecked, setAuthChecked] = useState(false);
  const [locale, setLocale] = useState<AdminLocale>(() =>
    typeof window !== 'undefined' ? detectAdminLocale() : 'en',
  );
  const [adminRole, setAdminRole] = useState<string | null>(null);
  const [sandboxDemoPasswordDefault, setSandboxDemoPasswordDefault] = useState(false);
  const [demoPwBannerDismissed, setDemoPwBannerDismissed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('aicom_hide_default_demo_pw_banner') === '1';
  });

  useEffect(() => {
    const token = localStorage.getItem('admin_token');
    if (!token) {
      window.location.href = '/admin/login';
    } else {
      setAuthChecked(true);
      prefetchAdminDashboard();
    }
    setLocale(detectAdminLocale());
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    api
      .getMe()
      .then((m) => {
        setAdminRole(m.role || null);
        setSandboxDemoPasswordDefault(Boolean(m.sandbox_demo_password_uses_default));
      })
      .catch(() => {
        setAdminRole(null);
        setSandboxDemoPasswordDefault(false);
      });
  }, [authChecked]);

  const renderTab = () => {
    if (!authChecked) return null;
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab />;
      case 'setup':
        return <SetupWizardTab adminRole={adminRole} />;
      case 'monitor':
        return <MonitorTab />;
      case 'products':
        return <PipelineTab />;
      case 'new-product':
        return <NewProductTab locale={locale} />;
      case 'workshop':
        return <WorkshopTab />;
      case 'pipeline':
        return <PipelineTab />;
      case 'agents':
        return <AgentsTab />;
      case 'providers':
        return <ProvidersTab />;
      case 'llm-logs':
        return <LLMLogsTab />;
      case 'agent-logs':
        return <AgentLogsTab />;
      case 'security':
        return <SecurityTab />;
      case 'files':
        return <FilesTabLazy />;
      case 'sandbox':
        return <SandboxTab />;
      case 'director':
        return <DirectorTab locale={locale} />;
      case 'discovery':
        return <DiscoveryTab locale={locale} />;
      case 'settings':
        return <SettingsTab />;
      case 'users':
        if (adminRole !== 'super_admin') {
          return <DashboardTab />;
        }
        return <UsersTab locale={locale} />;
      case 'chat':
        return <CorporateChatTab />;
      case 'brainstorming':
        return <BrainstormingTab />;
      case 'support-queue':
        return <SupportQueueTab locale={locale} />;
      case 'outreach':
        return <OutreachTab locale={locale} />;
      default:
        return <DashboardTab />;
    }
  };

  return (
    <div className="min-h-screen flex min-w-0">
      <Sidebar
        activeTab={activeTab}
        onTabChange={changeTab}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        locale={locale}
        onLocaleChange={(next) => {
          setLocale(next);
          saveAdminLocale(next);
        }}
        showUsersTab={adminRole === 'super_admin'}
      />

      <main className="flex-1 min-w-0 px-4 md:px-8 overflow-x-auto overflow-y-auto pt-[max(1rem,env(safe-area-inset-top))] md:pt-8 pb-[max(1rem,env(safe-area-inset-bottom))]">
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

        {authChecked ? <AdminShellOnboarding activeTab={activeTab} /> : null}

        {renderTab()}
      </main>
    </div>
  );
}
