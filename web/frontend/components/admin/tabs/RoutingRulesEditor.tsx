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

import { ROUTING_TASK_TYPES } from './ProviderFormModal';

export function RoutingRulesEditor({ providers }: { providers: ProviderStatus[] }) {
  const providerNames = providers.map(p => p.name);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadRules();
  }, []);

  const loadRules = async () => {
    setLoading(true);
    try {
      const data = await api.getRoutingRules();
      setRules(data);
    } catch (e) {
      // fallback: use defaults
      setRules(ROUTING_TASK_TYPES.map((tt) => ({
        task_type: tt,
        preferred_provider: 'auto',
        model_role: 'light',
        timeout_sec: 60,
        fallback_provider: null,
      })));
    } finally {
      setLoading(false);
    }
  };

  const updateRule = (index: number, field: string, value: any) => {
    setRules((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateRoutingRules(rules);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save routing rules:', e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-gray-500 text-sm">Loading routing rules...</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-medium flex items-center gap-2">
          <List className="w-4 h-4 text-indigo-400" />
          Routing Rules
        </h3>
        <div className="flex items-center gap-2">
          {saved && <span className="text-green-400 text-xs">Saved!</span>}
          <Button size="sm" onClick={handleSave} disabled={saving}>
            <Save className="w-3 h-3 mr-1" />
            {saving ? 'Saving...' : 'Save Rules'}
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-white/5">
              <th className="text-left py-2 pr-2">Task Type</th>
              <th className="text-left py-2 pr-2">Provider</th>
              <th className="text-left py-2 pr-2">Model</th>
              <th className="text-left py-2 pr-2">Timeout (s)</th>
              <th className="text-left py-2 pr-2">Fallback</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule, i) => (
              <tr key={rule.task_type} className="border-b border-white/5 hover:bg-white/5">
                <td className="py-2 pr-2 text-gray-300 whitespace-nowrap">{rule.task_type}</td>
                <td className="py-2 pr-2">
                  <select
                    className="w-full bg-white/5 border border-white/10 rounded px-1 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                    value={rule.preferred_provider || 'auto'}
                    onChange={(e) => updateRule(i, 'preferred_provider', e.target.value)}
                  >
                    <option value="auto" className="bg-gray-900">Auto (fastest available)</option>
                    {providerNames.map(name => (
                      <option key={name} value={name} className="bg-gray-900">{name}</option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-2">
                  <select
                    className="bg-white/5 border border-white/10 rounded px-1 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                    value={rule.model_role || 'light'}
                    onChange={(e) => updateRule(i, 'model_role', e.target.value)}
                  >
                    <option value="heavy" className="bg-gray-900">Heavy</option>
                    <option value="light" className="bg-gray-900">Light</option>
                  </select>
                </td>
                <td className="py-2 pr-2">
                  <input
                    type="number"
                    min={10}
                    max={600}
                    className="w-20 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                    value={rule.timeout_sec}
                    onChange={(e) => updateRule(i, 'timeout_sec', parseInt(e.target.value) || 60)}
                  />
                </td>
                <td className="py-2 pr-2">
                  <select
                    className="w-full bg-white/5 border border-white/10 rounded px-1 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                    value={rule.fallback_provider || ''}
                    onChange={(e) => updateRule(i, 'fallback_provider', e.target.value || null)}
                  >
                    <option value="" className="bg-gray-900">None</option>
                    {providerNames.map(name => (
                      <option key={name} value={name} className="bg-gray-900">{name}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

