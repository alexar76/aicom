'use client';

import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock,
  Cpu,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';
import { useMonitorMetrics } from '@/hooks/admin/useMonitorMetrics';
import { useMonitorActivityFeed } from '@/hooks/admin/useMonitorActivityFeed';
import { createEmptyDashboardData } from '@/lib/adminMetricsCache';
import {
  formatMonitorRelativeTime,
  getMonitorAgentDisplay,
} from '@/hooks/admin/monitorDisplayConfig';
import { type AdminLocale, t } from '@/lib/adminI18n';

function MetricValue({
  ready,
  value,
  className = 'text-white font-medium',
}: {
  ready: boolean;
  value: string | number;
  className?: string;
}) {
  if (!ready) {
    return (
      <span className="inline-flex items-center gap-1.5 text-gray-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
        …
      </span>
    );
  }
  return <span className={className}>{value}</span>;
}

export function MonitorTab({ locale }: { locale: AdminLocale }) {
  const {
    metrics,
    paused,
    setPaused,
    connectionStatus,
    initialLoading,
    bootRefreshing,
    pipelineReady,
    pipelineLoading,
    agentsReady,
    reloadMetrics,
  } = useMonitorMetrics();
  const { activityFeed, escEventFilter, setEscEventFilter } = useMonitorActivityFeed();
  const [expandedFleetAgent, setExpandedFleetAgent] = useState<string | null>(null);

  // ── Derived values ───────────────────────────────────────────────────
  const emptyMetrics = createEmptyDashboardData();
  const pipeline = metrics?.pipeline ?? emptyMetrics.pipeline;
  const resources = metrics?.resources ?? emptyMetrics.resources;
  const revenue = metrics?.revenue || {};
  const security = metrics?.security ?? emptyMetrics.security;
  const agentMetrics = metrics?.agent_metrics ?? emptyMetrics.agent_metrics ?? {};
  const directorStatus = metrics?.director_status ?? {
    report_count: 0,
    last_report_time: null as number | null,
    pending_decisions: 0,
    status: 'unknown',
  };
  const escalationSummary = metrics?.escalation_summary ?? {
    total_all_time: 0,
    recent_1h: 0,
    by_agent: {} as Record<string, unknown>,
    recent_events: [] as Array<Record<string, unknown>>,
  };

  const totalPipeline = pipeline.total_products || 0;
  const completedPipeline = pipeline.completed_products || 0;
  const sfRaw = pipeline.storefront_visible_products;
  const storefrontPending =
    Boolean(metrics?.dashboard_partial) && (sfRaw === null || sfRaw === undefined);
  const storefrontPipeline = sfRaw ?? 0;
  const activePipeline = pipeline.active_products || 0;
  const failedPipeline = pipeline.failed_products || 0;
  const completionPct =
    pipelineReady && totalPipeline > 0
      ? Math.round((completedPipeline / totalPipeline) * 100)
      : 0;

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
  const filteredEscalationEvents = (escalationSummary?.recent_events ?? []).filter((e: any) => {
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

  if (initialLoading && metrics == null) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin mx-auto mb-3" />
          <p className="text-gray-500 text-sm">{t(locale, 'common.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold text-white">Live Monitor</h2>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                connectionStatus === 'connected' ? 'bg-emerald-400 animate-pulse' :
                connectionStatus === 'connecting' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
              }`} />
              <span className="text-xs text-gray-500 capitalize">{connectionStatus}</span>
              {connectionStatus === 'connecting' && metrics ? (
                <span className="text-[10px] text-gray-600">· SSE (cached snapshot on screen)</span>
              ) : null}
            </div>
          </div>
          {bootRefreshing ? (
            <div className="flex w-full max-w-md items-center gap-2 rounded-lg border border-indigo-500/20 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-100/90">
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
              Refreshing snapshot from server…
            </div>
          ) : null}
        </div>
        <div className="flex w-full shrink-0 flex-wrap items-center justify-end gap-2 sm:w-auto">
          {pipelineLoading ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void reloadMetrics()}
              className="flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </Button>
          ) : null}
          <Button
            variant={paused ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPaused(!paused)}
            className="flex items-center justify-center gap-2"
          >
            {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            {paused ? 'Resume' : 'Pause'}
          </Button>
        </div>
      </div>

      {pipelineLoading ? (
        <p className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100/90">
          {connectionStatus === 'error'
            ? 'Live stream disconnected — showing last snapshot. Use Retry or check admin login / disk space.'
            : t(locale, 'dashboard.loadingLive')}
        </p>
      ) : null}

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
                {!pipelineLoading ? (
                  <>
                    <span className="text-3xl font-bold text-white">{completionPct}%</span>
                    <span className="text-xs text-gray-500">complete</span>
                  </>
                ) : (
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
                )}
              </div>
            </div>
            <div className="w-full min-w-0 space-y-2 text-sm sm:flex-1">
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-400">Total</span>
                <MetricValue ready={!pipelineLoading} value={totalPipeline} />
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-gray-400">Shipped builds</span>
                </span>
                <MetricValue
                  ready={!pipelineLoading}
                  value={completedPipeline}
                  className="text-emerald-400 font-medium"
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="text-gray-400">On storefront</span>
                </span>
                <MetricValue
                  ready={!storefrontPending}
                  value={storefrontPipeline}
                  className="text-cyan-400 font-medium"
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-blue-400" />
                  <span className="text-gray-400">Active</span>
                </span>
                <MetricValue
                  ready={!pipelineLoading}
                  value={activePipeline}
                  className="text-blue-400 font-medium"
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-gray-400">Needs rework</span>
                </span>
                <MetricValue
                  ready={!pipelineLoading}
                  value={failedPipeline}
                  className="text-amber-400 font-medium"
                />
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
          {pipelineLoading ? (
            <p className="text-sm text-gray-500 flex items-center gap-2 mb-4">
              <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
              {t(locale, 'dashboard.loadingLive')}
            </p>
          ) : null}
          <div className="space-y-5">
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">CPU</span>
                <span
                  className={`font-mono text-xs ${
                    !pipelineLoading
                      ? cpuPct > 80
                        ? 'text-red-400'
                        : cpuPct > 50
                          ? 'text-yellow-400'
                          : 'text-emerald-400'
                      : 'text-gray-500'
                  }`}
                >
                  {!pipelineLoading ? `${cpuPct.toFixed(1)}%` : '…'}
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    cpuPct > 80 ? 'bg-red-500' : cpuPct > 50 ? 'bg-yellow-500' : 'bg-emerald-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${!pipelineLoading ? Math.min(cpuPct, 100) : 0}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">Memory</span>
                <span
                  className={`font-mono text-xs ${
                    !pipelineLoading
                      ? memPct > 80
                        ? 'text-red-400'
                        : memPct > 50
                          ? 'text-yellow-400'
                          : 'text-emerald-400'
                      : 'text-gray-500'
                  }`}
                >
                  {!pipelineLoading ? `${memPct.toFixed(1)}%` : '…'}
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    memPct > 80 ? 'bg-red-500' : memPct > 50 ? 'bg-yellow-500' : 'bg-blue-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${!pipelineLoading ? Math.min(memPct, 100) : 0}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">Disk</span>
                <span
                  className={`font-mono text-xs ${
                    !pipelineLoading
                      ? diskPct > 80
                        ? 'text-red-400'
                        : diskPct > 50
                          ? 'text-yellow-400'
                          : 'text-emerald-400'
                      : 'text-gray-500'
                  }`}
                >
                  {!pipelineLoading ? `${diskPct.toFixed(1)}%` : '…'}
                </span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    diskPct > 80 ? 'bg-red-500' : diskPct > 50 ? 'bg-yellow-500' : 'bg-purple-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${!pipelineLoading ? Math.min(diskPct, 100) : 0}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
          </div>
          {/* Security badge */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Security</span>
              <Badge
                variant={
                  pipelineLoading
                    ? 'info'
                    : security.status === 'secure' || security.status === 'healthy'
                      ? 'success'
                      : 'error'
                }
              >
                {pipelineLoading ? '…' : security.status || 'unknown'}
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
              <div
                className={`flex h-11 w-11 shrink-0 items-center justify-center overflow-visible rounded-xl ${
                  directorStatus.status === 'active' ? 'bg-emerald-500/20' : 'bg-gray-500/20'
                }`}
              >
                <BarChart3
                  className={`h-6 w-6 ${
                    directorStatus.status === 'active' ? 'text-emerald-400' : 'text-gray-400'
                  }`}
                  strokeWidth={2}
                />
              </div>
              <div>
                <p className="text-sm text-white font-medium capitalize">
                  {!pipelineLoading ? directorStatus.status || 'unknown' : '…'}
                </p>
                <p className="text-xs text-gray-500">
                  {!pipelineLoading ? directorStatus.report_count || 0 : '…'} reports generated
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white/5 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-indigo-400">
                  {!pipelineLoading ? (directorStatus.pending_decisions ?? 0) : '…'}
                </p>
                <p className="text-xs text-gray-500 mt-1">Pending Decisions</p>
              </div>
              <div className="bg-white/5 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-purple-400">
                  {!pipelineLoading ? directorStatus.report_count || 0 : '…'}
                </p>
                <p className="text-xs text-gray-500 mt-1">Total Reports</p>
              </div>
            </div>
            {directorStatus.last_report_time && (
              <p className="text-xs text-gray-500">
                Last report: {formatMonitorRelativeTime(directorStatus.last_report_time)}
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
        {!agentsReady ? (
          <div className="text-center py-6">
            {!pipelineLoading ? (
              <>
                <Bot className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No agent metrics available yet.</p>
              </>
            ) : (
              <p className="text-gray-500 text-sm flex items-center justify-center gap-2">
                <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
                {t(locale, 'dashboard.loadingLive')}
              </p>
            )}
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
              const display = getMonitorAgentDisplay(type);
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
                        <span className="text-gray-300">{formatMonitorRelativeTime(info.last_active)}</span>
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
                        {entry.time ? formatMonitorRelativeTime(entry.time) : ''}
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
                  <option key={t} value={t}>{getMonitorAgentDisplay(t).label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {filteredEscalationEvents.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No escalations</p>
                <p className="text-xs text-gray-600 mt-1">All agents operating normally.</p>
              </div>
            ) : (
              filteredEscalationEvents.map((esc: any, i: number) => (
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
                      <p className="text-[10px] text-gray-600 mt-0.5">{formatMonitorRelativeTime(esc.timestamp)}</p>
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
