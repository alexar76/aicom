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

import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';

export function MonitorTab() {
  const [metrics, setMetrics] = useState<any>(null);
  const [activityFeed, setActivityFeed] = useState<any[]>([]);
  const [paused, setPaused] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');
  const [initialLoading, setInitialLoading] = useState(true);
  const [escEventFilter, setEscEventFilter] = useState<string>('all');
  /** Agent Fleet card: click green-dot tile to expand raw metrics JSON */
  const [expandedFleetAgent, setExpandedFleetAgent] = useState<string | null>(null);

  // Initial load from GET /dashboard (populates all fields including new ones)
  useEffect(() => {
    api.getDashboard().then((data) => {
      setMetrics(data);
      setInitialLoading(false);
    }).catch(() => setInitialLoading(false));
    // Load recent escalations as initial activity
    api.getEscalations(10).then((res) => {
      if (res.escalations?.length) {
        setActivityFeed(res.escalations.map((e: any) => ({
          type: 'escalation',
          agent: e.agent_type || 'system',
          message: e.error || e.action_taken || 'Escalation triggered',
          time: e.timestamp || Date.now(),
          severity: 'error',
        })));
      }
    }).catch(() => {});
    // Load latest agent logs for feed
    api.getAgentLogs(undefined, 20).then((res) => {
      if (res.logs?.length) {
        setActivityFeed((prev) => {
          const logEntries = res.logs.map((l: any) => ({
            type: 'agent_log',
            agent: l.agent || l.agent_type || 'unknown',
            message: l.message || l.content || '—',
            time: l.timestamp || l.time || Date.now(),
            severity: l.level || 'info',
          }));
          return [...logEntries, ...prev].slice(0, 100);
        });
      }
    }).catch(() => {});
  }, []);

  // SSE connection for real-time updates
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      setConnectionStatus('connecting');
      try {
        eventSource = new EventSource('/api/admin/metrics/stream');

        eventSource.onopen = () => {
          setConnectionStatus('connected');
        };

        eventSource.onmessage = (event) => {
          if (paused) return;
          try {
            const data = JSON.parse(event.data);
            setMetrics(data);
          } catch {
            // ignore parse errors
          }
        };

        eventSource.addEventListener('error', () => {
          setConnectionStatus('error');
          eventSource?.close();
          reconnectTimer = setTimeout(connect, 5000);
        });
      } catch {
        setConnectionStatus('error');
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      eventSource?.close();
      clearTimeout(reconnectTimer);
    };
  }, [paused]);

  // ── Derived values ───────────────────────────────────────────────────
  const pipeline = metrics?.pipeline || {};
  const resources = metrics?.resources || {};
  const revenue = metrics?.revenue || {};
  const security = metrics?.security || {};
  const agentMetrics = metrics?.agent_metrics || {};
  const directorStatus = metrics?.director_status || {};
  const escalationSummary = metrics?.escalation_summary || {};

  const totalPipeline = pipeline.total_products || 0;
  const completedPipeline = pipeline.completed_products || 0;
  const storefrontPipeline = pipeline.storefront_visible_products ?? 0;
  const activePipeline = pipeline.active_products || 0;
  const failedPipeline = pipeline.failed_products || 0;
  const completionPct = totalPipeline > 0 ? Math.round((completedPipeline / totalPipeline) * 100) : 0;

  /** Include virtual Designer (UX) after Architect when metrics only have worker logs (no designer.jsonl). */
  const fleetAgentTypes = useMemo(() => {
    const raw = Object.keys(agentMetrics);
    const withDesigner =
      raw.includes('designer') || !raw.includes('architect')
        ? raw
        : (() => {
            const i = raw.indexOf('architect');
            return [...raw.slice(0, i + 1), 'designer', ...raw.slice(i + 1)];
          })();
    const preferred = [
      'analyst',
      'pm',
      'methodologist',
      'architect',
      'designer',
      'developer',
      'qa',
      'security',
      'devops',
      'marketing',
      'sales',
      'evolution_analyst',
    ];
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const p of preferred) {
      if (withDesigner.includes(p) && !seen.has(p)) {
        ordered.push(p);
        seen.add(p);
      }
    }
    for (const k of withDesigner) {
      if (!seen.has(k)) {
        ordered.push(k);
        seen.add(k);
      }
    }
    return ordered;
  }, [agentMetrics]);

  const agentTypes = fleetAgentTypes;
  const recentEscalations = (escalationSummary.recent_events || []).filter((e: any) => {
    if (escEventFilter === 'all') return true;
    return e.agent_type === escEventFilter;
  });

  const cpuPct = resources.cpu_percent ?? 0;
  const memPct = resources.memory_percent ?? 0;
  const diskPct = resources.disk_percent ?? 0;

  // ── Ring gauge SVG ───────────────────────────────────────────────────
  const ringRadius = 64;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference - (completionPct / 100) * ringCircumference;

  // ── Agent type display config ────────────────────────────────────────
  const agentDisplayConfig: Record<string, { label: string; color: string }> = {
    analyst: { label: 'Analyst', color: '#38bdf8' },
    pm: { label: 'PM', color: '#60a5fa' },
    architect: { label: 'Architect', color: '#a78bfa' },
    designer: { label: 'Designer', color: '#d946ef' },
    developer: { label: 'Developer', color: '#34d399' },
    devops: { label: 'DevOps', color: '#f472b6' },
    qa: { label: 'QA', color: '#fbbf24' },
    security: { label: 'Security', color: '#ef4444' },
    marketing: { label: 'Marketing', color: '#2dd4bf' },
    sales: { label: 'Sales', color: '#fb923c' },
    evolution_analyst: { label: 'Evolution', color: '#818cf8' },
    methodologist: { label: 'Methodologist', color: '#0ea5e9' },
  };

  const getAgentDisplay = (type: string) => agentDisplayConfig[type] || { label: type, color: '#9ca3af' };

  // ── Format helpers ───────────────────────────────────────────────────
  const fmtTime = (ts: number | null | undefined) => {
    if (!ts) return '—';
    // ts is Unix seconds, Date.now() is milliseconds
    const secs = Math.floor((Date.now() - ts * 1000) / 1000);
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
  };

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin mx-auto mb-3" />
          <p className="text-gray-500 text-sm">Connecting to metrics stream...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold text-white">Live Monitor</h2>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected' ? 'bg-emerald-400 animate-pulse' :
              connectionStatus === 'connecting' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
            }`} />
            <span className="text-xs text-gray-500 capitalize">{connectionStatus}</span>
          </div>
        </div>
        <Button
          variant={paused ? 'primary' : 'secondary'}
          size="sm"
          onClick={() => setPaused(!paused)}
          className="flex w-full shrink-0 items-center justify-center gap-2 sm:w-auto"
        >
          {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          {paused ? 'Resume' : 'Pause'}
        </Button>
      </div>

      <DemoReplayMonitorSection demoReplay={metrics?.demo_replay} />

      {/* Top row: Pipeline Gauge + System Health + Director Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Pipeline Ring Gauge ── */}
        <GlassCard>
          <h3 className="text-sm font-medium text-gray-400 mb-4">Pipeline Completion</h3>
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
            <div className="relative h-36 w-36 shrink-0">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 144 144">
                <circle cx="72" cy="72" r={ringRadius} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
                <circle
                  cx="72" cy="72" r={ringRadius} fill="none"
                  stroke="url(#ringGradient)" strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={ringCircumference}
                  strokeDashoffset={ringOffset}
                  className="transition-all duration-1000 ease-out"
                />
                <defs>
                  <linearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#a78bfa" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold text-white">{completionPct}%</span>
                <span className="text-xs text-gray-500">complete</span>
              </div>
            </div>
            <div className="w-full min-w-0 space-y-2 text-sm sm:flex-1">
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-400">Total</span>
                <span className="text-white font-medium">{totalPipeline}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-gray-400">Shipped builds</span>
                </span>
                <span className="text-emerald-400 font-medium">{completedPipeline}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="text-gray-400">On storefront</span>
                </span>
                <span className="text-cyan-400 font-medium">{storefrontPipeline}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-blue-400" />
                  <span className="text-gray-400">Active</span>
                </span>
                <span className="text-blue-400 font-medium">{activePipeline}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-red-400" />
                  <span className="text-gray-400">Failed</span>
                </span>
                <span className="text-red-400 font-medium">{failedPipeline}</span>
              </div>
            </div>
          </div>
          {pipeline.state_distribution && (
            <div className="mt-4 pt-4 border-t border-white/5">
              <div className="flex flex-wrap gap-2">
                {Object.entries(pipeline.state_distribution).map(([state, count]) => (
                  <Badge key={state} variant="info" className="text-xs">
                    {state}: {count as number}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </GlassCard>

        {/* ── System Health ── */}
        <GlassCard>
          <h3 className="text-sm font-medium text-gray-400 mb-4">System Health</h3>
          <div className="space-y-5">
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">CPU</span>
                <span className={`font-mono text-xs ${cpuPct > 80 ? 'text-red-400' : cpuPct > 50 ? 'text-yellow-400' : 'text-emerald-400'}`}>
                  {cpuPct.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    cpuPct > 80 ? 'bg-red-500' : cpuPct > 50 ? 'bg-yellow-500' : 'bg-emerald-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(cpuPct, 100)}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">Memory</span>
                <span className={`font-mono text-xs ${memPct > 80 ? 'text-red-400' : memPct > 50 ? 'text-yellow-400' : 'text-emerald-400'}`}>
                  {memPct.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    memPct > 80 ? 'bg-red-500' : memPct > 50 ? 'bg-yellow-500' : 'bg-blue-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(memPct, 100)}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">Disk</span>
                <span className={`font-mono text-xs ${diskPct > 80 ? 'text-red-400' : diskPct > 50 ? 'text-yellow-400' : 'text-emerald-400'}`}>
                  {diskPct.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    diskPct > 80 ? 'bg-red-500' : diskPct > 50 ? 'bg-yellow-500' : 'bg-purple-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(diskPct, 100)}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
          </div>
          {/* Security badge */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Security</span>
              <Badge variant={security.status === 'secure' ? 'success' : 'error'}>
                {security.status || 'unknown'}
              </Badge>
            </div>
            {security.failed_logins_15min > 0 && (
              <p className="text-xs text-red-400 mt-1">
                {security.failed_logins_15min} failed logins in last 15min
              </p>
            )}
          </div>
        </GlassCard>

        {/* ── Director Status ── */}
        <GlassCard>
          <h3 className="text-sm font-medium text-gray-400 mb-4">Director AI</h3>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                directorStatus.status === 'active' ? 'bg-emerald-500/20' : 'bg-gray-500/20'
              }`}>
                <BarChart3 className={`w-5 h-5 ${
                  directorStatus.status === 'active' ? 'text-emerald-400' : 'text-gray-400'
                }`} />
              </div>
              <div>
                <p className="text-sm text-white font-medium capitalize">{directorStatus.status || 'unknown'}</p>
                <p className="text-xs text-gray-500">
                  {directorStatus.report_count || 0} reports generated
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white/5 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-indigo-400">{directorStatus.pending_decisions ?? 0}</p>
                <p className="text-xs text-gray-500 mt-1">Pending Decisions</p>
              </div>
              <div className="bg-white/5 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-purple-400">{directorStatus.report_count || 0}</p>
                <p className="text-xs text-gray-500 mt-1">Total Reports</p>
              </div>
            </div>
            {directorStatus.last_report_time && (
              <p className="text-xs text-gray-500">
                Last report: {fmtTime(directorStatus.last_report_time)}
              </p>
            )}
          </div>
        </GlassCard>
      </div>

      {/* Middle section: Agent Grid */}
      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-400">Agent Fleet</h3>
          <span className="text-xs text-gray-500">{agentTypes.length} agents</span>
        </div>
        {Object.keys(agentMetrics).length === 0 ? (
          <div className="text-center py-6">
            <Bot className="w-8 h-8 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No agent metrics available yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {agentTypes.map((type) => {
              const infoRaw =
                agentMetrics[type] ??
                (type === 'designer' ? agentMetrics['architect'] : undefined);
              const info = infoRaw ?? {
                total_entries: 0,
                recent_entries: 0,
                recent_errors: 0,
                last_active: 0,
                status: 'idle',
              };
              const display = getAgentDisplay(type);
              const statusColor = info.status === 'active' ? 'bg-emerald-400' :
                                  info.status === 'busy' ? 'bg-yellow-400' :
                                  info.status === 'error' ? 'bg-red-400' : 'bg-gray-500';
              const expanded = expandedFleetAgent === type;
              return (
                <motion.div
                  key={type}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className={`bg-white/5 rounded-xl p-3 transition-colors border border-transparent ${
                    expanded ? 'border-indigo-500/40 bg-white/[0.08]' : 'hover:bg-white/10'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setExpandedFleetAgent(expanded ? null : type)}
                    className="w-full text-left rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                    title="Show metrics from logs"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`w-2.5 h-2.5 shrink-0 rounded-full ${statusColor} ${info.status === 'active' ? 'animate-pulse' : ''}`} />
                      <span className="text-sm font-medium text-white truncate">{display.label}</span>
                      <ChevronRight className={`w-3.5 h-3.5 ml-auto text-gray-500 transition-transform shrink-0 ${expanded ? 'rotate-90' : ''}`} />
                    </div>
                    <div className="space-y-1 text-xs pointer-events-none">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Tasks</span>
                        <span className="text-gray-300">{info.total_entries || 0}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Errors</span>
                        <span className={info.recent_errors > 0 ? 'text-red-400' : 'text-gray-300'}>
                          {info.recent_errors || 0}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Active</span>
                        <span className="text-gray-300">{fmtTime(info.last_active)}</span>
                      </div>
                    </div>
                  </button>
                  {expanded && (
                    <div className="mt-3 pt-3 border-t border-white/10">
                      <p className="text-[10px] text-gray-500 mb-1">Raw agent_metrics[{type}]</p>
                      <pre className="text-[10px] text-gray-400 whitespace-pre-wrap break-all max-h-40 overflow-y-auto bg-black/25 rounded-lg p-2 font-mono leading-relaxed">
                        {(() => {
                          try {
                            return JSON.stringify(info, null, 2);
                          } catch {
                            return String(info);
                          }
                        })()}
                      </pre>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        )}
      </GlassCard>

      {/* Bottom row: Activity Feed + Escalations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Activity Feed ── */}
        <GlassCard>
          <h3 className="text-sm font-medium text-gray-400 mb-4">Activity Feed</h3>
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {activityFeed.length === 0 ? (
              <div className="text-center py-8">
                <Activity className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">Waiting for activity...</p>
              </div>
            ) : (
              activityFeed.slice(0, 50).map((entry, i) => {
                const severityColor = entry.severity === 'error' ? 'text-red-400' :
                                      entry.severity === 'warn' || entry.severity === 'warning' ? 'text-yellow-400' :
                                      entry.severity === 'info' ? 'text-blue-400' : 'text-gray-400';
                return (
                  <div
                    key={`${entry.time}-${i}`}
                    className="flex flex-col gap-1 border-b border-white/5 py-2 text-xs last:border-0 sm:flex-row sm:items-start sm:gap-2 sm:py-1.5"
                  >
                    <div className="flex shrink-0 items-center gap-2 sm:w-28">
                      <Circle className={`h-1.5 w-1.5 shrink-0 ${severityColor}`} fill="currentColor" />
                      <span className="font-mono text-[10px] text-gray-500 sm:text-xs">
                        {entry.time ? fmtTime(entry.time) : ''}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1 sm:flex sm:min-w-0 sm:gap-2">
                      <span className="shrink-0 font-medium text-gray-400">{entry.agent || entry.type}:</span>
                      <span className="break-words text-gray-500">{entry.message}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </GlassCard>

        {/* ── Escalations ── */}
        <GlassCard>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-sm font-medium text-gray-400">Escalations</h3>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
              <span className={`text-xs ${(escalationSummary.recent_1h || 0) > 0 ? 'text-red-400' : 'text-gray-500'}`}>
                {(escalationSummary.recent_1h || 0)} in last hour
              </span>
              <select
                value={escEventFilter}
                onChange={(e) => setEscEventFilter(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-xs text-gray-400 sm:w-auto sm:py-1"
              >
                <option value="all">All</option>
                {agentTypes.map((t) => (
                  <option key={t} value={t}>{getAgentDisplay(t).label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {recentEscalations.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No escalations</p>
                <p className="text-xs text-gray-600 mt-1">All agents operating normally.</p>
              </div>
            ) : (
              recentEscalations.map((esc: any, i: number) => (
                <div key={i} className="flex items-start gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors">
                  <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-red-300">
                        {esc.agent_type || 'system'}
                      </span>
                      <Badge variant="error" className="text-[10px] px-1.5 py-0">
                        {esc.action_taken || 'escalated'}
                      </Badge>
                    </div>
                    {esc.error && (
                      <p className="text-xs text-gray-400 mt-0.5 truncate">{esc.error}</p>
                    )}
                    {esc.timestamp && (
                      <p className="text-[10px] text-gray-600 mt-0.5">{fmtTime(esc.timestamp)}</p>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
