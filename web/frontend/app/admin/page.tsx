'use client';

import { useEffect, useState } from 'react';
import { Cpu, Menu } from 'lucide-react';
import BrainstormingTab from '@/components/BrainstormingTab';
import SupportQueueTab from '@/components/SupportQueueTab';
import OutreachTab from '@/components/OutreachTab';
import { Sidebar } from '@/components/admin/AdminSidebar';
import {
  AgentsTab,
  AgentLogsTab,
  CorporateChatTab,
  DashboardTab,
  DirectorTab,
  DiscoveryTab,
  FilesTab,
  LLMLogsTab,
  MonitorTab,
  NewProductTab,
  PipelineTab,
  ProvidersTab,
  SandboxTab,
  SecurityTab,
  SettingsTab,
  UsersTab,
} from '@/components/admin/AdminTabs';
import { AdminLocale, detectAdminLocale, saveAdminLocale } from '@/lib/adminI18n';
import api from '@/lib/api';

const ADMIN_TAB_IDS = new Set([
  'dashboard',
  'monitor',
  'pipeline',
  'new-product',
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
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [authChecked, setAuthChecked] = useState(false);
  const [locale, setLocale] = useState<AdminLocale>(() =>
    typeof window !== 'undefined' ? detectAdminLocale() : 'en',
  );
  const [adminRole, setAdminRole] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('admin_token');
    if (!token) {
      window.location.href = '/admin/login';
    } else {
      setAuthChecked(true);
    }
    setLocale(detectAdminLocale());
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    api
      .getMe()
      .then((m) => setAdminRole(m.role || null))
      .catch(() => setAdminRole(null));
  }, [authChecked]);

  useEffect(() => {
    if (!authChecked) return;
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab && ADMIN_TAB_IDS.has(tab)) {
      setActiveTab(tab);
    }
  }, [authChecked]);

  const renderTab = () => {
    if (!authChecked) return null;
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab />;
      case 'monitor':
        return <MonitorTab />;
      case 'products':
        return <PipelineTab />;
      case 'new-product':
        return <NewProductTab />;
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
        return <FilesTab />;
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
        onTabChange={setActiveTab}
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
          <Cpu className="w-6 h-6 text-indigo-400" />
        </div>

        {renderTab()}
      </main>
    </div>
  );
}
