'use client';

import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
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
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme, parseDatetimeLocalToUnixSeconds } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

const AGENT_LOG_FILTER_TYPES = [
  'analyst',
  'pm',
  'methodologist',
  'architect',
  'developer',
  'devops',
  'qa',
  'security',
  'marketing',
  'sales',
  'evolution_analyst',
  'audit',
] as const;

export function AgentLogsTab({ locale }: { locale: AdminLocale }) {
  const searchParams = useSearchParams();
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [logCount, setLogCount] = useState(0);
  const [logTotal, setLogTotal] = useState(0);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const filter = agentFilter && agentFilter !== 'all' ? agentFilter : undefined;
      const since = parseDatetimeLocalToUnixSeconds(dateFrom);
      const until = parseDatetimeLocalToUnixSeconds(dateTo);
      const data = await api.getAgentLogs(filter, 3000, since, until);
      setLogs(data.logs || []);
      setLogCount(data.count || 0);
      setLogTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load agent logs:', err);
    } finally {
      setLoading(false);
    }
  }, [agentFilter, dateFrom, dateTo]);

  useEffect(() => {
    const a = searchParams.get('agentLog')?.trim();
    if (!a) return;
    if (a === 'all') {
      setAgentFilter('all');
      return;
    }
    if ((AGENT_LOG_FILTER_TYPES as readonly string[]).includes(a)) {
      setAgentFilter(a);
    }
  }, [searchParams]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const getAgentBadgeColor = (agent: string) => {
    const colors: Record<string, string> = {
      pm: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
      architect: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
      developer: 'bg-green-500/20 text-green-300 border-green-500/30',
      devops: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
      qa: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
      security: 'bg-red-500/20 text-red-300 border-red-500/30',
      marketing: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
      sales: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
      evolution_analyst: 'bg-teal-500/20 text-teal-300 border-teal-500/30',
      methodologist: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
      audit: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
    };
    return colors[agent] || 'bg-gray-500/20 text-gray-300 border-gray-500/30';
  };

  const formatLogTime = (timestamp: number) => {
    const d = new Date(timestamp * 1000);
    return d.toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };

  const filteredLogs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return logs.filter((log) => {
      if (onlyErrors && !String(log?.message || '').toLowerCase().includes('error')) return false;
      if (!q) return true;
      const agent = String(log?.agent || '').toLowerCase();
      const msg = String(log?.message || '').toLowerCase();
      const extra = JSON.stringify(log).toLowerCase();
      return agent.includes(q) || msg.includes(q) || extra.includes(q);
    });
  }, [logs, query, onlyErrors]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <h2 className="text-xl font-semibold text-white shrink-0">{t(locale, 'agentLogs.title')}</h2>
        <div className="flex min-w-0 flex-1 flex-col gap-2 sm:max-w-3xl lg:ml-auto">
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search message / agent / payload..."
              className="min-w-0 w-full sm:min-w-[12rem] sm:flex-1"
            />
            <label className="text-xs text-gray-400 flex shrink-0 items-center gap-1.5">
              <input
                type="checkbox"
                checked={onlyErrors}
                onChange={(e) => setOnlyErrors(e.target.checked)}
                className="accent-indigo-500"
              />
              Errors only
            </label>
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none sm:w-auto"
            >
              <option value="all">All Agents</option>
              {AGENT_LOG_FILTER_TYPES.map((agent) => (
                <option key={agent} value={agent}>{agent}</option>
              ))}
            </select>
            <label className="flex min-w-[10rem] flex-1 flex-col gap-0.5 text-[10px] text-gray-500 sm:max-w-[11rem]">
              <span>From (local)</span>
              <input
                type="datetime-local"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-gray-200 focus:border-indigo-500/50 focus:outline-none"
              />
            </label>
            <label className="flex min-w-[10rem] flex-1 flex-col gap-0.5 text-[10px] text-gray-500 sm:max-w-[11rem]">
              <span>To (local)</span>
              <input
                type="datetime-local"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-gray-200 focus:border-indigo-500/50 focus:outline-none"
              />
            </label>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void loadLogs()}
              disabled={loading}
              className="w-full shrink-0 sm:w-auto"
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <FilterResetSummary
        onReset={() => {
          setQuery('');
          setOnlyErrors(false);
          setAgentFilter('all');
          setDateFrom('');
          setDateTo('');
        }}
        summary={`Showing ${filteredLogs.length} filtered / ${logCount} loaded / ${logTotal} in time window`}
      />

      <GlassCard>
        {loading ? (
          <div className="text-center py-12">
            <RefreshCw className="w-8 h-8 text-gray-600 mx-auto mb-3 animate-spin" />
            <p className="text-gray-500">Loading agent logs...</p>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="text-center py-12">
            <List className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No logs match current filters.</p>
            <p className="text-xs text-gray-600 mt-1">
              {agentFilter !== 'all'
                ? `Try clearing search/errors for "${agentFilter}".`
                : 'Try clearing filters or refresh.'}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredLogs.map((log, i) => (
              <div key={i} className="py-3 first:pt-0 last:pb-0">
                <div
                  className="flex items-start gap-3 cursor-pointer"
                  onClick={() => setExpandedIndex(expandedIndex === i ? null : i)}
                >
                  <Badge className={`text-xs font-mono border ${getAgentBadgeColor(log.agent)}`}>
                    {log.agent}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-300 truncate">{log.message}</p>
                    <p className="text-xs text-gray-600 mt-0.5">{formatLogTime(log.time)}</p>
                  </div>
                  <ChevronRight
                    className={`w-4 h-4 text-gray-600 mt-1 transition-transform ${
                      expandedIndex === i ? 'rotate-90' : ''
                    }`}
                  />
                </div>
                {expandedIndex === i && (
                  <div className="mt-3 ml-0 pl-0 border-t border-white/5 pt-3">
                    <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap overflow-auto max-h-64">
                      {JSON.stringify(log, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
