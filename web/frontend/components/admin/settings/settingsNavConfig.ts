import type { LucideIcon } from 'lucide-react';
import {
  Archive,
  Container,
  Database,
  FileText,
  GitBranch,
  Globe,
  HardDrive,
  MessageCircle,
  Package,
  Pause,
  Palette,
  Send,
  Shield,
  SlidersHorizontal,
  TrainFront,
  Video,
  Zap,
} from 'lucide-react';

export type SettingsSectionId =
  | 'factory-hold'
  | 'director-pipeline'
  | 'quality'
  | 'director-standup'
  | 'pipeline-db'
  | 'git-remote'
  | 'docker'
  | 'auto-publish'
  | 'product-catalog'
  | 'railway'
  | 'content'
  | 'telegram'
  | 'host-disk'
  | 'factory-backup'
  | 'account-security'
  | 'demo-replay'
  | 'theme';

export type SettingsNavItem = {
  id: SettingsSectionId;
  labelKey: string;
  icon: LucideIcon;
};

/** Order matches Settings tab layout (top → bottom). */
export const SETTINGS_NAV_ITEMS: SettingsNavItem[] = [
  { id: 'factory-hold', labelKey: 'settings.factoryHold.title', icon: Pause },
  { id: 'director-pipeline', labelKey: 'settings.section.directorPipeline', icon: Zap },
  { id: 'quality', labelKey: 'settings.quality.title', icon: SlidersHorizontal },
  { id: 'director-standup', labelKey: 'settings.section.directorStandup', icon: MessageCircle },
  { id: 'pipeline-db', labelKey: 'settings.pipelineDb.title', icon: Database },
  { id: 'git-remote', labelKey: 'settings.section.gitRemote', icon: GitBranch },
  { id: 'docker', labelKey: 'settings.section.docker', icon: Container },
  { id: 'auto-publish', labelKey: 'settings.section.autoPublish', icon: Globe },
  { id: 'product-catalog', labelKey: 'settings.section.productCatalog', icon: Package },
  { id: 'railway', labelKey: 'settings.section.railway', icon: TrainFront },
  { id: 'content', labelKey: 'settings.nav.contentGroup', icon: FileText },
  { id: 'telegram', labelKey: 'settings.section.telegram', icon: Send },
  { id: 'host-disk', labelKey: 'settings.nav.hostDisk', icon: HardDrive },
  { id: 'factory-backup', labelKey: 'settings.factoryBackup.title', icon: Archive },
  { id: 'account-security', labelKey: 'settings.nav.security', icon: Shield },
  { id: 'demo-replay', labelKey: 'settings.nav.demoReplay', icon: Video },
  { id: 'theme', labelKey: 'settings.section.theme', icon: Palette },
];
