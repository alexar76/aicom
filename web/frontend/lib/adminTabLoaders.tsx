'use client';

import dynamic from 'next/dynamic';
import type { ComponentType } from 'react';
import { Loader2 } from 'lucide-react';

// Admin tabs pass varying prop shapes (locale, adminRole, …); dynamic() erases at runtime.
type TabComponent = ComponentType<any>;

function TabLoading({ label }: { label: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-gray-400">
      <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
      <p className="text-sm">{label}</p>
    </div>
  );
}

function lazyTabNamed<M extends Record<string, unknown>, K extends keyof M>(
  importFn: () => Promise<M>,
  exportName: K,
  label: string,
) {
  return dynamic(
    async () => {
      const mod = await importFn();
      return { default: mod[exportName] as TabComponent };
    },
    {
      ssr: false,
      loading: () => <TabLoading label={label} />,
    },
  );
}

function lazyTabDefault(importFn: () => Promise<{ default: unknown }>, label: string) {
  return dynamic(
    async () => {
      const mod = await importFn();
      return { default: mod.default as TabComponent };
    },
    {
      ssr: false,
      loading: () => <TabLoading label={label} />,
    },
  );
}

export const DashboardTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/DashboardTab'),
  'DashboardTab',
  'Loading dashboard…',
);
export const SetupWizardTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/SetupWizardTab'),
  'SetupWizardTab',
  'Loading setup…',
);
export const MonitorTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/MonitorTab'),
  'MonitorTab',
  'Loading monitor…',
);
export const FactoryFloorTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/FactoryFloorTab'),
  'FactoryFloorTab',
  'Loading factory floor…',
);
export const TimeTravelReplayTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/TimeTravelReplayTab'),
  'TimeTravelReplayTab',
  'Loading replay…',
);
export const ProductShowcaseTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/ProductShowcaseTab'),
  'ProductShowcaseTab',
  'Loading showcase…',
);
export const BlogPostsTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/BlogPostsTab'),
  'BlogPostsTab',
  'Loading blog…',
);
export const PromptImprovementTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/PromptImprovementTab'),
  'PromptImprovementTab',
  'Loading prompt loop…',
);
export const PipelineTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/PipelineTab'),
  'PipelineTab',
  'Loading pipeline…',
);
export const NewProductTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/NewProductTab'),
  'NewProductTab',
  'Loading new product…',
);
export const WorkshopTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/WorkshopTab'),
  'WorkshopTab',
  'Loading workshop…',
);
export const AgentsTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/AgentsTab'),
  'AgentsTab',
  'Loading agents…',
);
export const ProvidersTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/ProvidersTab'),
  'ProvidersTab',
  'Loading providers…',
);
export const LLMLogsTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/LLMLogsTab'),
  'LLMLogsTab',
  'Loading LLM logs…',
);
export const AgentLogsTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/AgentLogsTab'),
  'AgentLogsTab',
  'Loading agent logs…',
);
export const SecurityTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/SecurityTab'),
  'SecurityTab',
  'Loading security…',
);
export const FilesTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/FilesTab'),
  'FilesTab',
  'Loading files…',
);
export const SandboxTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/SandboxTab'),
  'SandboxTab',
  'Loading sandbox…',
);
export const DirectorTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/DirectorTab'),
  'DirectorTab',
  'Loading director…',
);
export const DiscoveryTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/DiscoveryTab'),
  'DiscoveryTab',
  'Loading discovery…',
);
export const SettingsTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/SettingsTab'),
  'SettingsTab',
  'Loading settings…',
);
export const CorporateChatTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/CorporateChatTab'),
  'CorporateChatTab',
  'Loading chat…',
);
export const UsersTabLazy = lazyTabNamed(
  () => import('@/components/admin/tabs/UsersTab'),
  'UsersTab',
  'Loading users…',
);
export const BrainstormingTabLazy = lazyTabDefault(
  () => import('@/components/BrainstormingTab'),
  'Loading brainstorming…',
);
export const SupportQueueTabLazy = lazyTabDefault(
  () => import('@/components/SupportQueueTab'),
  'Loading support queue…',
);
export const OutreachTabLazy = lazyTabDefault(
  () => import('@/components/OutreachTab'),
  'Loading outreach…',
);
