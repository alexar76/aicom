'use client';

import React, { useEffect, useState, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Cpu,
  Bot,
  Shield,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Plus,
  Send,
  Activity,
  Users,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  MessageCircle,
  Menu,
  X,
  Trash2,
  Edit3,
  RefreshCw,
  Globe,
  ToggleLeft,
  ToggleRight,
  Save,
  List,
  ScrollText,
  ChevronRight,
  Terminal,
  Radio,
  Pause,
  Play,
  Gauge,
  Circle,
  Star,
  ExternalLink,
  Zap,
  GitBranch,
  Container,
  Layers,
  FlaskConical,
  BrainCircuit,
  ClipboardList,
  Inbox,
  Megaphone,
  Store,
  Loader2,
  Upload,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Modal } from '@/components/ui/Modal';
import {
  FilterControlsPanel,
  FilterNumberInput,
  FilterResetSummary,
  FilterSelect,
} from '@/components/admin/FilterControls';
import BrainstormingTab from '@/components/BrainstormingTab';
import SupportQueueTab from '@/components/SupportQueueTab';
import OutreachTab from '@/components/OutreachTab';
import { QRCodeSVG } from 'qrcode.react';
import api, {
  DashboardData,
  ProviderStatus,
  AgentStatus,
  CreateProviderPayload,
  RoutingRule,
  ChatMessage,
  DemoReplayAdminConfig,
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

export function AgentsTab() {
  const [agents, setAgents] = useState<AgentStatus[]>(
    () => INITIAL_AGENTS_TAB_ROWS as AgentStatus[]
  );

  useEffect(() => {
    api.getAgents().then(setAgents).catch(() => {});
  }, []);

  /** getAgents() runs buildAgentsTabRows (always includes Designer); state seeds from INITIAL_* before fetch */
  const agentList = agents;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white mb-4">AI Agents</h2>
      <p className="text-xs text-gray-500 mb-4 max-w-2xl">
        <strong className="text-gray-400">Designer</strong> is not a separate worker process: UX direction lives in the
        Architect output (<code className="text-cyan-400/90">ui_experience</code>) and is implemented by Developer. The
        card mirrors Architect status and task counts for visibility. Intermediate stages{' '}
        <strong className="text-gray-400">design critic</strong> and <strong className="text-gray-400">hardening</strong>{' '}
        run inside the pipeline worker but do not appear as separate cards here. Marketplace chat uses{' '}
        <strong className="text-gray-400">Lumen</strong> (buyer chat via Support API, not Microsoft Copilot), not this roster.
      </p>
      <div className="grid md:grid-cols-2 gap-4">
        {agentList.map((agent, i) => (
          <motion.div
            key={agent.type}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <GlassCard>
              <div className="flex items-center gap-4">
                <div className="text-3xl">{getAgentIcon(agent.type)}</div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="text-white font-medium capitalize">
                      {agent.type === 'designer'
                        ? 'Designer (UX)'
                        : agent.type === 'methodologist'
                          ? 'Methodologist'
                          : agent.type.replace('_', ' ')}
                    </h3>
                    <Badge
                      variant={
                        agent.status === 'running'
                          ? 'success'
                          : agent.status === 'error'
                          ? 'error'
                          : 'info'
                      }
                    >
                      {agent.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {agent.tasks_completed} tasks completed
                  </p>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
