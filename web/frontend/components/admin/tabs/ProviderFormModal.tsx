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

export const ROUTING_TASK_TYPES = [
  'architecture_design',
  'code_generation',
  'pm_analysis',
  'qa_testing',
  'security_scan',
  'devops_setup',
  'marketing_copy',
  'sales_response',
  'evolution_analysis',
] as const;

const emptyProviderForm: CreateProviderPayload = {
  name: '',
  provider_type: 'openai_compatible',
  base_url: '',
  api_key_env: null,
  enabled: true,
  models: { heavy: '', light: '' },
  capabilities: {
    context_window: 128000,
    max_tokens: 32000,
    supports_vision: false,
    supports_streaming: true,
  },
  priority: 10,
  health_check_endpoint: '/v1/models',
};

export function ProviderFormModal({
  isOpen,
  onClose,
  initial,
  onSaved,
}: {
  isOpen: boolean;
  onClose: () => void;
  initial: CreateProviderPayload | null;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<CreateProviderPayload>(emptyProviderForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setForm(initial ? { ...emptyProviderForm, ...initial } : { ...emptyProviderForm });
      setError('');
    }
  }, [isOpen, initial]);

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('Provider name is required'); return; }
    if (!form.base_url?.trim()) { setError('Base URL is required'); return; }
    setSaving(true);
    setError('');
    try {
      if (initial?.name && initial.name === form.name) {
        await api.updateProvider(form.name, form);
      } else {
        await api.createProvider(form);
      }
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.message || 'Failed to save provider');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (key: string, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initial ? 'Edit Provider' : 'Add Provider'} size="xl">
      <div className="space-y-4">
        {error && <div className="text-red-400 text-sm bg-red-500/10 rounded p-2">{error}</div>}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-400 text-xs mb-1">Name *</label>
            <Input
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="e.g. deepseek_api"
              disabled={!!initial}
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Type</label>
            <select
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
              value={form.provider_type || 'openai_compatible'}
              onChange={(e) => updateField('provider_type', e.target.value)}
            >
              <option value="openai_compatible" className="bg-gray-900">OpenAI Compatible</option>
              <option value="anthropic" className="bg-gray-900">Anthropic Cloud</option>
              <option value="ollama" className="bg-gray-900">Ollama</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-gray-400 text-xs mb-1">Base URL *</label>
          <Input
            value={form.base_url || ''}
            onChange={(e) => updateField('base_url', e.target.value)}
            placeholder="e.g. https://api.deepseek.com/v1"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-400 text-xs mb-1">API Key</label>
            <Input
              type="password"
              value={form.api_key || ''}
              onChange={(e) => updateField('api_key', e.target.value || null)}
              placeholder={initial ? '•••••••••• (unchanged if empty)' : 'sk-...'}
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Health Check Endpoint</label>
            <Input
              value={form.health_check_endpoint || '/v1/models'}
              onChange={(e) => updateField('health_check_endpoint', e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-400 text-xs mb-1">Heavy Model</label>
            <Input
              value={form.models?.heavy || ''}
              onChange={(e) => updateField('models', { ...form.models, heavy: e.target.value })}
              placeholder="e.g. deepseek-reasoner"
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Light Model</label>
            <Input
              value={form.models?.light || ''}
              onChange={(e) => updateField('models', { ...form.models, light: e.target.value })}
              placeholder="e.g. deepseek-chat"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-gray-400 text-xs mb-1">Context Window</label>
            <Input
              type="number"
              value={form.capabilities?.context_window || 128000}
              onChange={(e) => updateField('capabilities', { ...form.capabilities, context_window: parseInt(e.target.value) || 128000 })}
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Max Tokens</label>
            <Input
              type="number"
              value={form.capabilities?.max_tokens || 32000}
              onChange={(e) => updateField('capabilities', { ...form.capabilities, max_tokens: parseInt(e.target.value) || 32000 })}
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Priority</label>
            <Input
              type="number"
              value={form.priority || 10}
              onChange={(e) => updateField('priority', parseInt(e.target.value) || 10)}
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={form.enabled ?? true}
              onChange={(e) => updateField('enabled', e.target.checked)}
              className="rounded bg-white/5 border-white/10"
            />
            Enabled
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={form.capabilities?.supports_streaming ?? true}
              onChange={(e) => updateField('capabilities', { ...form.capabilities, supports_streaming: e.target.checked })}
              className="rounded bg-white/5 border-white/10"
            />
            Streaming
          </label>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? 'Saving...' : initial ? 'Update Provider' : 'Add Provider'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

