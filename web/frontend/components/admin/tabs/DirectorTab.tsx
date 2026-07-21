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
import { useDirectorData } from '@/hooks/admin/useDirectorData';
import { useDirectorReplay } from '@/hooks/admin/useDirectorReplay';
import { useDirectorCockpit } from '@/hooks/admin/useDirectorCockpit';

export function DirectorTab({ locale }: { locale: AdminLocale }) {
  const {
    reports,
    analysisData,
    benchmarkData,
    expandedReport,
    setExpandedReport,
    decisions,
    actionInProgress,
    benchmarkTriggering,
    renamingCatalog,
    remediatingCatalog,
    feedbackSummary,
    discoveryQueue,
    discoveryMeta,
    discoveryLoading,
    directorQuery,
    setDirectorQuery,
    directorCategoryFilter,
    setDirectorCategoryFilter,
    directorMinScore,
    setDirectorMinScore,
    handleApprove,
    handleReject,
    handleTriggerBenchmark,
    handleRenameCatalogProducts,
    handleRemediateCatalogCompliance,
    refreshDiscovery,
    directorDiscoveryCategories,
    filteredDirectorDiscoveryQueue,
    filteredPendingDecisions,
    filteredReports,
    formatDecisionTime,
    getActionLabel,
  } = useDirectorData(locale);

  const {
    replayProductId,
    setReplayProductId,
    replaySessions,
    replaySessionId,
    replayTimeline,
    replayLoading,
    loadReplaySessions,
    loadReplayTimeline,
  } = useDirectorReplay();

  const {
    cockpitProductId,
    setCockpitProductId,
    cockpit,
    cockpitLoading,
    loadCockpit,
    executeProtocol,
  } = useDirectorCockpit();

  return (
    <div className="space-y-4">
      <GlassCard className="border border-indigo-500/25 bg-gradient-to-br from-indigo-950/35 to-transparent">
        <p className="text-sm text-gray-300 leading-relaxed">
          One pipeline feeds Director telemetry whether products came from autonomous discovery (research + ideas) or from a
          customer brief. Decisions and reports apply uniformly — there is no parallel “cheap” track for manual submissions.
        </p>
      </GlassCard>
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold text-white">Director AI</h2>
        <Badge variant="info" className="text-xs">
          {analysisData ? `${analysisData.report_count} reports` : '...'}
        </Badge>
        {benchmarkData?.alerts && benchmarkData.alerts.length > 0 && (
          <Badge variant="error" className="text-xs">
            benchmark alerts: {benchmarkData.alerts.length}
          </Badge>
        )}
        {decisions.pending_count > 0 && (
          <Badge variant="error" className="text-xs">
            {decisions.pending_count} pending
          </Badge>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refreshDiscovery(false)}
          disabled={discoveryLoading}
        >
          {discoveryLoading ? t(locale, 'discovery.refreshing') : t(locale, 'discovery.directorRefresh')}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refreshDiscovery(true)}
          disabled={discoveryLoading}
        >
          {discoveryLoading ? t(locale, 'discovery.queueing') : t(locale, 'discovery.directorQueueTop')}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleTriggerBenchmark}
          disabled={benchmarkTriggering}
        >
          {benchmarkTriggering ? 'Running…' : 'Run Benchmark Now'}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRenameCatalogProducts}
          disabled={renamingCatalog}
        >
          {renamingCatalog ? 'Renaming…' : 'Rename Existing Catalog Products Now'}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRemediateCatalogCompliance}
          disabled={remediatingCatalog}
        >
          {remediatingCatalog ? 'Hardening…' : 'Run Full Catalog Compliance Remediation'}
        </Button>
      </div>

      <GlassCard>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-lg font-medium text-white">{t(locale, 'discovery.ideaQueueSection')}</h3>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info" className="text-xs">
              {discoveryQueue.length} {t(locale, 'discovery.ideasLabel')}
            </Badge>
            <Badge variant="info" className="text-xs">
              {t(locale, 'discovery.signalsLabel')} {discoveryMeta?.signals_total ?? 0}
            </Badge>
          </div>
        </div>
        <FilterControlsPanel
          onReset={() => {
            setDirectorQuery('');
            setDirectorCategoryFilter('all');
            setDirectorMinScore('');
          }}
          summary={`${filteredDirectorDiscoveryQueue.length} / ${discoveryQueue.length}`}
          gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2"
        >
          <Input
            value={directorQuery}
            onChange={(e) => setDirectorQuery(e.target.value)}
            placeholder="Search discovery/decisions/reports..."
          />
          <FilterSelect
            value={directorCategoryFilter}
            onChange={(e) => setDirectorCategoryFilter(e.target.value)}
          >
            <option value="all">All categories</option>
            {directorDiscoveryCategories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </FilterSelect>
          <FilterNumberInput
            value={directorMinScore}
            onChange={(e) => setDirectorMinScore(e.target.value)}
            placeholder="Min score (e.g. 8)"
          />
        </FilterControlsPanel>
        {discoveryMeta?.signal_pruning?.removed ? (
          <p className="text-xs text-amber-300 mb-3">
            {tVars(locale, 'discovery.pruning', { n: discoveryMeta.signal_pruning.removed })}
          </p>
        ) : null}
        {filteredDirectorDiscoveryQueue.length === 0 ? (
          <p className="text-sm text-gray-400">{t(locale, 'discovery.noRankedYet')}</p>
        ) : (
          <div className="space-y-2">
            {filteredDirectorDiscoveryQueue.slice(0, 8).map((idea: any, idx: number) => (
              <div key={`${idea.idea}-${idx}`} className="p-3 rounded-lg bg-white/5 border border-white/10">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs text-gray-400">#{idx + 1} · {idea.category}</span>
                  <span className="text-xs text-cyan-300">
                    score {Number(idea.score_total || 0).toFixed(2)} · balanced {Number(idea.balanced_score || idea.score_total || 0).toFixed(2)}
                  </span>
                </div>
                <p className="text-sm text-white">{idea.idea}</p>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {benchmarkData?.scorecard && (
        <GlassCard>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-medium text-white">Regression League Scorecard</h3>
            <Badge variant="info" className="text-xs">
              {benchmarkData.scorecard.runs_total ?? 0} runs
            </Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Pass-rate 24h avg</p>
              <p className="text-xl font-semibold text-cyan-300">
                {benchmarkData.scorecard.pass_rate_last_24h_avg ?? '—'}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Pass-rate 7d avg</p>
              <p className="text-xl font-semibold text-indigo-300">
                {benchmarkData.scorecard.pass_rate_last_7d_avg ?? '—'}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Latest run pass-rate</p>
              <p className="text-xl font-semibold text-purple-300">
                {benchmarkData.scorecard?.latest?.pass_rate ?? '—'}
              </p>
            </div>
          </div>
          {benchmarkData.alerts && benchmarkData.alerts.length > 0 && (
            <div className="mt-3 space-y-2">
              {benchmarkData.alerts.map((a: any, idx: number) => (
                <div key={idx} className="text-xs p-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-200">
                  {a.message} (value={a.value}, threshold={a.threshold}, window={a.window})
                </div>
              ))}
            </div>
          )}
          {benchmarkData?.status && (
            <div className="mt-3 text-xs text-gray-400">
              benchmark status: {String(benchmarkData.status.status || 'unknown')}
              {benchmarkData.status.started_at ? ` • started ${new Date(benchmarkData.status.started_at * 1000).toLocaleString()}` : ''}
              {benchmarkData.status.ended_at ? ` • ended ${new Date(benchmarkData.status.ended_at * 1000).toLocaleString()}` : ''}
            </div>
          )}
          {benchmarkData?.investor_metrics && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
              <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                <p className="text-gray-400">Production readiness index</p>
                <p className="text-cyan-300 font-semibold">{benchmarkData.investor_metrics.production_readiness_index}</p>
              </div>
              <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                <p className="text-gray-400">Trend vs 7d</p>
                <p className="text-indigo-300 font-semibold">{benchmarkData.investor_metrics.trend_vs_7d}</p>
              </div>
              <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                <p className="text-gray-400">95% CI (7d)</p>
                <p className="text-purple-300 font-semibold">
                  [{benchmarkData.investor_metrics.confidence_interval_95.low}, {benchmarkData.investor_metrics.confidence_interval_95.high}]
                </p>
              </div>
            </div>
          )}
        </GlassCard>
      )}

      {feedbackSummary && (
        <GlassCard>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-medium text-white">Real User Feedback (7d)</h3>
            <Badge variant="info" className="text-xs">
              {feedbackSummary.count ?? 0} items
            </Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Bug reports</p>
              <p className="text-xl font-semibold text-red-300">
                {feedbackSummary.by_classification?.bug ?? 0}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Feature requests</p>
              <p className="text-xl font-semibold text-cyan-300">
                {feedbackSummary.by_classification?.feature_request ?? 0}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-white/5 border border-white/10">
              <p className="text-gray-400">Improvements</p>
              <p className="text-xl font-semibold text-indigo-300">
                {feedbackSummary.by_classification?.improvement ?? 0}
              </p>
            </div>
          </div>
          {Array.isArray(feedbackSummary.top_products) && feedbackSummary.top_products.length > 0 && (
            <div className="mt-3 space-y-2">
              {feedbackSummary.top_products.slice(0, 5).map((p: any) => (
                <div key={p.product_id} className="flex flex-col gap-1 rounded-lg border border-white/10 bg-white/5 p-2 text-xs text-gray-300 sm:flex-row sm:items-center sm:justify-between">
                  <span className="font-mono break-all">{p.product_id}</span>
                  <span className="text-gray-400 sm:text-right">feedback={p.count} • bugs={p.bugs} • avg={p.avg_rating}</span>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      )}

      <GlassCard>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-lg font-medium text-white">Session Replay (Telemetry Timeline)</h3>
          <Badge variant="info" className="text-xs">{replayTimeline.length} events</Badge>
        </div>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            placeholder="prod-xxxxxxxxxxxx"
            value={replayProductId}
            onChange={(e) => setReplayProductId(e.target.value)}
            className="w-full max-w-full sm:max-w-xs"
          />
          <Button size="sm" variant="secondary" onClick={loadReplaySessions} disabled={replayLoading} className="w-full sm:w-auto">
            {replayLoading ? 'Loading…' : 'Load Sessions'}
          </Button>
        </div>
        {replaySessions.length > 0 && (
          <div className="mb-3 space-y-2">
            {replaySessions.slice(0, 8).map((s: any) => (
              <button
                key={s.session_id}
                type="button"
                onClick={() => loadReplayTimeline(s.session_id)}
                className={`w-full text-left text-xs p-2 rounded-lg border ${
                  replaySessionId === s.session_id
                    ? 'border-indigo-500/50 bg-indigo-500/10 text-indigo-200'
                    : 'border-white/10 bg-white/5 text-gray-300'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono">{s.session_id}</span>
                  <span>{s.event_count} events</span>
                </div>
              </button>
            ))}
          </div>
        )}
        {replayTimeline.length > 0 && (
          <div className="max-h-72 overflow-auto space-y-1 pr-1">
            {replayTimeline.slice(-120).map((ev: any, idx: number) => (
              <div key={idx} className="text-xs p-2 rounded-lg bg-white/5 border border-white/10 text-gray-300">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-cyan-300">{ev.event_type}</span>
                  <span className="text-gray-500">
                    {ev.timestamp ? new Date(ev.timestamp * 1000).toLocaleTimeString() : '—'}
                  </span>
                </div>
                <pre className="text-[10px] whitespace-pre-wrap text-gray-400">
                  {JSON.stringify(ev.data || {}, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-lg font-medium text-white">Go / No-Go Cockpit</h3>
          {cockpit?.go_no_go && (
            <Badge variant={cockpit.go_no_go === 'go' ? 'success' : 'error'} className="text-xs">
              {String(cockpit.go_no_go).toUpperCase()}
            </Badge>
          )}
        </div>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            placeholder="prod-xxxxxxxxxxxx"
            value={cockpitProductId}
            onChange={(e) => setCockpitProductId(e.target.value)}
            className="w-full max-w-full sm:max-w-xs"
          />
          <Button size="sm" variant="secondary" onClick={loadCockpit} disabled={cockpitLoading} className="w-full sm:w-auto">
            {cockpitLoading ? 'Loading…' : 'Evaluate'}
          </Button>
          <Button size="sm" onClick={executeProtocol} disabled={cockpitLoading} className="w-full sm:w-auto">
            Execute Release Protocol
          </Button>
        </div>
        {cockpit?.checks && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
            {Object.entries(cockpit.checks).map(([k, v]) => (
              <div key={k} className="text-xs p-2 rounded-lg bg-white/5 border border-white/10 flex items-center justify-between">
                <span className="text-gray-300">{k}</span>
                <span className={v ? 'text-emerald-300' : 'text-red-300'}>{v ? 'pass' : 'fail'}</span>
              </div>
            ))}
          </div>
        )}
        {Array.isArray(cockpit?.issues) && cockpit.issues.length > 0 && (
          <div className="space-y-1">
            {cockpit.issues.map((x: string, i: number) => (
              <div key={i} className="text-xs p-2 rounded bg-red-500/10 border border-red-500/30 text-red-200">
                {x}
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* ── Pending Decisions ── */}
      {filteredPendingDecisions.length > 0 && (
        <GlassCard>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-medium text-white">Pending Decisions</h3>
            <Badge variant="error" className="text-xs">
              {filteredPendingDecisions.length} need review
            </Badge>
          </div>
          <div className="space-y-3">
            {filteredPendingDecisions.map((d: any) => (
              <div key={d.id} className="p-3 bg-white/5 rounded-xl border border-yellow-500/20">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-white">{getActionLabel(d.action)}</span>
                      {d.target && (
                        <Badge variant="info" className="text-[10px]">{d.target}</Badge>
                      )}
                    </div>
                    {d.reason && (
                      <p className="text-xs text-gray-400 mb-1">{d.reason}</p>
                    )}
                    {d.impact && (
                      <p className="text-xs text-gray-500">Impact: {d.impact}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-600">
                      {(d.created_at || d.applied_at) && <span>Created {formatDecisionTime(d.created_at || d.applied_at)}</span>}
                      {d.new_value !== undefined && <span>Value: {d.new_value}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => handleApprove(d.id)}
                      disabled={actionInProgress === d.id}
                      className="flex items-center gap-1"
                    >
                      {actionInProgress === d.id ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3 h-3" />
                      )}
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleReject(d.id)}
                      disabled={actionInProgress === d.id}
                      className="flex items-center gap-1"
                    >
                      <X className="w-3 h-3" />
                      Reject
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Analysis previews from director/analysis endpoint */}
      {analysisData?.reports && analysisData.reports.length > 0 && (
        <GlassCard>
          <h3 className="text-lg font-medium text-white mb-3">Recent Analysis Reports</h3>
          <div className="divide-y divide-white/5">
            {analysisData.reports.slice(0, 5).map((r: any, i: number) => (
              <div key={i} className="py-2 first:pt-0 last:pb-0">
                <div
                  className="flex cursor-pointer items-center justify-between gap-2"
                  onClick={() => setExpandedReport(expandedReport === i ? null : i)}
                >
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-indigo-400" />
                    <span className="text-sm text-gray-300">{r.filename}</span>
                  </div>
                  <ChevronRight className={`w-4 h-4 text-gray-600 transition-transform ${expandedReport === i ? 'rotate-90' : ''}`} />
                </div>
                {expandedReport === i && r.content && (
                  <div className="mt-2 p-3 bg-white/5 rounded-xl">
                    <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap max-h-80 overflow-auto">
                      {r.content}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* ── Decision History ── */}
      {decisions.applied.length > 0 && (
        <GlassCard>
          <h3 className="text-lg font-medium text-white mb-3">Decision History</h3>
          <div className="space-y-1">
            {decisions.applied.slice(0, 10).map((d: any) => (
              <div key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 p-2 rounded-lg hover:bg-white/5 transition-colors text-xs">
                {d.status === 'approved' || d.status === 'applied' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                ) : d.status === 'rejected' ? (
                  <X className="w-4 h-4 text-red-400 shrink-0" />
                ) : (
                  <Clock className="w-4 h-4 text-gray-500 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <span className="text-gray-300 font-medium">{getActionLabel(d.action)}</span>
                  {d.target && <span className="text-gray-500"> → {d.target}</span>}
                  {d.reason && <span className="text-gray-500 ml-1">— {d.reason}</span>}
                </div>
                <Badge variant={d.status === 'rejected' ? 'error' : 'success'} className="text-[10px]">
                  {d.status}
                </Badge>
                <span className="ml-auto w-full shrink-0 text-right text-gray-600 sm:ml-0 sm:w-24">
                  {formatDecisionTime(d.applied_at || d.approved_at || d.rejected_at)}
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Legacy report listing */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-3">Report Archive</h3>
        {filteredReports.length === 0 ? (
          <div className="text-center py-8">
            <BarChart3 className="w-10 h-10 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No Director AI reports yet.</p>
            <p className="text-xs text-gray-600 mt-1">
              Reports are generated every 4 hours automatically.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredReports.map((report, i) => (
              <div key={i} className="flex flex-col gap-3 rounded-xl bg-white/5 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm text-white font-medium">{report.filename}</p>
                  {report.date && (
                    <p className="text-xs text-gray-500">{report.date}{report.period ? ` • ${report.period}` : ''}</p>
                  )}
                </div>
                <Button variant="secondary" size="sm" className="w-full shrink-0 sm:w-auto">
                  View
                </Button>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
