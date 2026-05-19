'use client';

import React, { useCallback, useEffect, useState, useMemo, useRef } from 'react';
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
  LLMLogsSummary,
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme, parseDatetimeLocalToUnixSeconds } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

// ── LLM Call Logs Tab ────────────────────────────────────────────────────

const REPORT_CHART_COLORS = ['#818cf8', '#34d399', '#fbbf24', '#f472b6', '#22d3ee', '#a78bfa', '#fb923c', '#4ade80'];

const DARK_CHART_TOOLTIP = {
  contentStyle: {
    background: '#0f172a',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: 8,
    boxShadow: '0 4px 12px rgba(0,0,0,0.45)',
  },
  labelStyle: { color: '#f8fafc', fontWeight: 600 },
  itemStyle: { color: '#e2e8f0' },
};

/** Rows per request; use ``offset`` on the server to load older pages without pulling the whole JSONL into the browser. */
const LLM_LOG_PAGE_SIZE = 200;

/** Parse log entry time for sorting (newest first). Naive ISO datetimes match backend: UTC. */
function llmLogTimeMs(log: Record<string, unknown>): number {
  const t = log.timestamp ?? log.created_at ?? log.time;
  if (t == null || t === '') return 0;
  if (typeof t === 'number') {
    return t > 1e12 ? t : t * 1000;
  }
  const s = String(t).trim();
  let ms: number;
  if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !/[zZ]$/.test(s) && !/[+-]\d{2}:\d{2}$/.test(s)) {
    ms = Date.parse(s.endsWith('Z') ? s : `${s}Z`);
  } else {
    ms = Date.parse(s);
  }
  return Number.isFinite(ms) ? ms : 0;
}

export function LLMLogsTab({ locale }: { locale: AdminLocale }) {
  const searchParams = useSearchParams();
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterProvider, setFilterProvider] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [serverSummary, setServerSummary] = useState<LLMLogsSummary | null>(null);
  const [totalRows, setTotalRows] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreGuard = useRef(false);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'ok' | 'error'>('all');
  const [agentTypeFilter, setAgentTypeFilter] = useState('all');

  useEffect(() => {
    const a = searchParams.get('llmAgent')?.trim();
    if (a) setAgentTypeFilter(a);
  }, [searchParams]);

  const sortedLogs = useMemo(
    () => [...logs].sort((a, b) => llmLogTimeMs(b) - llmLogTimeMs(a)),
    [logs]
  );

  const filteredLogs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sortedLogs.filter((log) => {
      if (statusFilter === 'ok' && !log.success) return false;
      if (statusFilter === 'error' && log.success) return false;
      if (agentTypeFilter !== 'all' && String(log.agent_type || '') !== agentTypeFilter) return false;
      if (!q) return true;
      const provider = String(log.provider || '').toLowerCase();
      const model = String(log.model || '').toLowerCase();
      const prompt = String(log.prompt_preview || '').toLowerCase();
      const resp = String(log.response_preview || '').toLowerCase();
      const err = String(log.error || '').toLowerCase();
      const taskType = String(log.task_type || '').toLowerCase();
      return (
        provider.includes(q) ||
        model.includes(q) ||
        prompt.includes(q) ||
        resp.includes(q) ||
        err.includes(q) ||
        taskType.includes(q)
      );
    });
  }, [sortedLogs, query, statusFilter, agentTypeFilter]);

  const filteredReport = useMemo(() => {
    let sumCost = 0;
    let withCost = 0;
    let sumPrompt = 0;
    let sumCompletion = 0;
    let sumTokens = 0;
    let callsWithInOut = 0;
    const byProvider: Record<string, number> = {};
    const byRole: Record<string, number> = {};
    const byAgent: Record<string, number> = {};

    for (const log of filteredLogs) {
      const c = log.estimated_cost_usd;
      if (typeof c === 'number' && Number.isFinite(c)) {
        sumCost += c;
        withCost += 1;
      }
      const p = log.prompt_tokens;
      const co = log.completion_tokens;
      if (typeof p === 'number' && Number.isFinite(p)) sumPrompt += p;
      if (typeof co === 'number' && Number.isFinite(co)) sumCompletion += co;
      const tu = log.tokens_used;
      if (typeof tu === 'number' && Number.isFinite(tu)) sumTokens += tu;
      if (typeof p === 'number' && typeof co === 'number') callsWithInOut += 1;

      const prov = String(log.provider || 'unknown');
      byProvider[prov] = (byProvider[prov] || 0) + (typeof c === 'number' ? c : 0);

      const role = String(log.model_role || 'unknown');
      byRole[role] = (byRole[role] || 0) + (typeof c === 'number' ? c : 0);

      const ag = String(log.agent_type || '—');
      byAgent[ag] = (byAgent[ag] || 0) + (typeof c === 'number' ? c : 0);
    }

    const providerPie = Object.entries(byProvider)
      .map(([name, value]) => ({ name, value }))
      .filter((x) => x.value > 0)
      .sort((a, b) => b.value - a.value);

    const roleBar = Object.entries(byRole)
      .map(([name, cost]) => ({ name, cost }))
      .filter((x) => x.cost > 0)
      .sort((a, b) => b.cost - a.cost);

    const agentBar = Object.entries(byAgent)
      .filter(([k]) => k !== '—')
      .map(([name, cost]) => ({ name, cost }))
      .filter((x) => x.cost > 0)
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 14);

    return {
      sumCost,
      withCost,
      sumPrompt,
      sumCompletion,
      sumTokens,
      callsWithInOut,
      providerPie,
      roleBar,
      agentBar,
    };
  }, [filteredLogs]);

  const displayReport = useMemo(() => {
    if (serverSummary != null) {
      const s = serverSummary;
      return {
        sumCost: s.estimated_cost_usd ?? 0,
        withCost: s.calls_with_cost_estimate ?? 0,
        sumPrompt: s.prompt_tokens ?? 0,
        sumCompletion: s.completion_tokens ?? 0,
        sumTokens: s.tokens_used_sum ?? 0,
        callsWithInOut: s.calls_with_prompt_completion_tokens ?? 0,
        providerPie: s.by_provider ?? [],
        roleBar: s.by_role ?? [],
        agentBar: s.by_agent ?? [],
        rangeTotal: s.matching_in_range ?? 0,
      };
    }
    return { ...filteredReport, rangeTotal: filteredLogs.length };
  }, [serverSummary, filteredReport, filteredLogs.length]);

  const showSummaryCard =
    !loading && (serverSummary != null || filteredLogs.length > 0);

  const usdTooltipFmt = (v: number) =>
    `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;

  const refreshLogs = useCallback(async () => {
    setLoading(true);
    try {
      const since = parseDatetimeLocalToUnixSeconds(dateFrom);
      const until = parseDatetimeLocalToUnixSeconds(dateTo);
      const data = await api.getLLMLogs(
        LLM_LOG_PAGE_SIZE,
        filterProvider || undefined,
        since,
        until,
        0,
      );
      setLogs(data.logs || []);
      setTotalRows(typeof data.total === 'number' ? data.total : (data.logs || []).length);
      setServerSummary(data.summary ?? null);
    } catch {
      setLogs([]);
      setTotalRows(0);
      setServerSummary(null);
    } finally {
      setLoading(false);
    }
  }, [filterProvider, dateFrom, dateTo]);

  const loadMoreLogs = useCallback(async () => {
    if (loadingMoreGuard.current) return;
    const offset = logs.length;
    if (totalRows > 0 && offset >= totalRows) return;
    loadingMoreGuard.current = true;
    setLoadingMore(true);
    try {
      const since = parseDatetimeLocalToUnixSeconds(dateFrom);
      const until = parseDatetimeLocalToUnixSeconds(dateTo);
      const data = await api.getLLMLogs(
        LLM_LOG_PAGE_SIZE,
        filterProvider || undefined,
        since,
        until,
        offset,
      );
      const chunk = data.logs || [];
      if (chunk.length === 0) return;
      setLogs((prev) => [...prev, ...chunk]);
    } catch {
      /* keep existing rows */
    } finally {
      loadingMoreGuard.current = false;
      setLoadingMore(false);
    }
  }, [filterProvider, dateFrom, dateTo, logs.length, totalRows]);

  useEffect(() => {
    void refreshLogs();
  }, [refreshLogs]);

  const hasMoreFromServer = totalRows > 0 && logs.length < totalRows;

  // Extract unique provider names for filter
  const providers = [...new Set(logs.map((l) => l.provider))].sort();
  const agentTypesInSelect = useMemo(() => {
    const s = new Set(logs.map((l) => String(l.agent_type || '')).filter(Boolean));
    if (agentTypeFilter !== 'all') s.add(agentTypeFilter);
    return [...s].sort();
  }, [logs, agentTypeFilter]);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white mb-1">{t(locale, 'llmLogs.title')}</h2>
      <p className="text-xs text-gray-500 mb-4">
        Estimates use input/output rates when the API reports prompt and completion tokens; otherwise blended $/Mtok and
        heavy/light provider rates from routing (
        <code className="text-gray-400">llm_pricing.example.yaml</code>) — not a vendor invoice. The table loads{' '}
        <strong className="text-gray-400">{LLM_LOG_PAGE_SIZE}</strong> rows at a time (newest first); use{' '}
        <strong className="text-gray-400">Load more</strong> for older pages. With a time range, totals and charts on the
        server cover <strong className="text-gray-400">every</strong> matching call, not only the loaded rows.
      </p>

      {/* Filtered summary + charts */}
      {showSummaryCard && (
        <GlassCard className="p-4 overflow-hidden">
          <div className="flex flex-col gap-6">
            {serverSummary != null && (
              <p className="text-[11px] text-amber-200/90 -mt-1">
                Totals below are for the selected time range on the server ({serverSummary.matching_in_range} calls). Search
                / status / agent filters only narrow the list, not these figures.
              </p>
            )}
            <div className="flex flex-col xl:flex-row gap-6 xl:items-stretch">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 flex-1 min-w-0">
                <div className="rounded-xl border border-white/10 bg-gradient-to-br from-emerald-950/40 to-slate-900/40 p-3">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Est. total</p>
                  <p className="text-lg font-semibold text-emerald-300 tabular-nums">
                    ${displayReport.sumCost.toFixed(4)}
                  </p>
                  <p className="text-[10px] text-gray-600 mt-1">{displayReport.withCost} calls with cost</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Prompt tokens</p>
                  <p className="text-lg font-medium text-gray-200 tabular-nums">
                    {displayReport.sumPrompt.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Completion tokens</p>
                  <p className="text-lg font-medium text-gray-200 tabular-nums">
                    {displayReport.sumCompletion.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Total tokens (logged)</p>
                  <p className="text-lg font-medium text-gray-200 tabular-nums">
                    {displayReport.sumTokens.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 col-span-2 sm:col-span-1 lg:col-span-2">
                  <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">In/out split in logs</p>
                  <p className="text-sm text-gray-300">
                    {displayReport.callsWithInOut} / {displayReport.rangeTotal} calls
                  </p>
                  <p className="text-[10px] text-gray-600 mt-1">Older rows may lack prompt/completion counts.</p>
                </div>
              </div>

              <div className="w-full xl:w-[min(100%,380px)] shrink-0 h-[220px]">
                <p className="text-xs font-medium text-gray-400 mb-2">Est. cost by provider</p>
                {displayReport.providerPie.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={displayReport.providerPie}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={52}
                        outerRadius={78}
                        paddingAngle={2}
                      >
                        {displayReport.providerPie.map((_, i) => (
                          <Cell key={i} fill={REPORT_CHART_COLORS[i % REPORT_CHART_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value: number) => usdTooltipFmt(value)}
                        {...DARK_CHART_TOOLTIP}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-600 text-sm">No cost data</div>
                )}
              </div>

              <div className="w-full xl:w-[min(100%,380px)] shrink-0 h-[220px]">
                <p className="text-xs font-medium text-gray-400 mb-2">Est. cost by model role</p>
                {displayReport.roleBar.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={displayReport.roleBar} layout="vertical" margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
                      <YAxis type="category" dataKey="name" width={56} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <Tooltip
                        formatter={(value: number) => usdTooltipFmt(value)}
                        {...DARK_CHART_TOOLTIP}
                      />
                      <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
                        {displayReport.roleBar.map((_, i) => (
                          <Cell key={i} fill={REPORT_CHART_COLORS[(i + 2) % REPORT_CHART_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-600 text-sm">No role data</div>
                )}
              </div>
            </div>

            {displayReport.agentBar.length > 0 && (
              <div className="w-full h-[240px]">
                <p className="text-xs font-medium text-gray-400 mb-2">Est. cost by agent (top)</p>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={displayReport.agentBar} margin={{ left: 8, right: 8, top: 8, bottom: 48 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} angle={-35} textAnchor="end" height={60} interval={0} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip
                      formatter={(value: number) => usdTooltipFmt(value)}
                      {...DARK_CHART_TOOLTIP}
                    />
                    <Bar dataKey="cost" fill="#818cf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </GlassCard>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-end">
          <div className="flex flex-col gap-1 min-w-0">
            <label className="text-[10px] uppercase tracking-wide text-gray-500">From (local)</label>
            <Input
              type="datetime-local"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full min-w-0 lg:w-[11.5rem]"
            />
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <label className="text-[10px] uppercase tracking-wide text-gray-500">To (local)</label>
            <Input
              type="datetime-local"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full min-w-0 lg:w-[11.5rem]"
            />
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search provider/model/task/prompt/response/error..."
            className="min-w-0 w-full sm:min-w-[14rem] sm:flex-1 sm:max-w-xl"
          />
          <select
            value={filterProvider}
            onChange={(e) => setFilterProvider(e.target.value)}
            className="glass-input w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none sm:w-auto sm:py-1.5"
          >
            <option value="">All Providers</option>
            {providers.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | 'ok' | 'error')}
            className="glass-input w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none sm:w-auto sm:py-1.5"
          >
            <option value="all">Status: all</option>
            <option value="ok">Status: success</option>
            <option value="error">Status: error</option>
          </select>
          <select
            value={agentTypeFilter}
            onChange={(e) => setAgentTypeFilter(e.target.value)}
            className="glass-input w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none sm:w-auto sm:py-1.5"
          >
            <option value="all">All agents</option>
            {agentTypesInSelect.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <FilterResetSummary
            onReset={() => {
              setQuery('');
              setStatusFilter('all');
              setAgentTypeFilter('all');
              setFilterProvider('');
              setDateFrom('');
              setDateTo('');
            }}
            summary={`${filteredLogs.length} visible · ${logs.length} loaded / ${totalRows || logs.length} on server · est. $${displayReport.sumCost.toFixed(4)} (${displayReport.withCost} calls w/ cost)`}
            className="text-xs text-gray-500 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4 min-w-0 pr-1"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refreshLogs()}
            className="w-full shrink-0 sm:w-auto"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      <GlassCard>
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full mx-auto mb-3" />
            <p className="text-gray-500 text-sm">Loading logs...</p>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12">
            <ScrollText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No LLM calls in the current server filter.</p>
            <p className="text-xs text-gray-600 mt-1">
              Try another provider or time range, or refresh after new traffic.
            </p>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="space-y-4 py-8 text-center">
            <ScrollText className="mx-auto mb-2 h-10 w-10 text-gray-600" />
            <p className="text-gray-500">No rows match your search / status / agent filters.</p>
            <p className="text-xs text-gray-600">{logs.length} calls loaded from server — clear text filters to see them.</p>
            {hasMoreFromServer && (
              <div className="flex justify-center pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={loadingMore}
                  onClick={() => void loadMoreLogs()}
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                      Loading…
                    </>
                  ) : (
                    <>Load more ({logs.length} / {totalRows})</>
                  )}
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {filteredLogs.map((log, i) => (
              <div
                key={`${String(log.timestamp)}-${log.provider}-${i}`}
                className="flex items-start gap-3 py-2.5 px-3 border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors rounded-lg"
              >
                <div className="flex-shrink-0 mt-0.5">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      log.success
                        ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50'
                        : 'bg-red-500 shadow-sm shadow-red-500/50'
                    }`}
                  />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                    <span className="text-xs font-medium text-indigo-300">
                      {log.provider}
                    </span>
                    <span className="text-xs text-gray-500">•</span>
                    <span className="text-xs text-gray-400 truncate">
                      {log.model || 'unknown'}
                    </span>
                    {typeof log.agent_type === 'string' && log.agent_type ? (
                      <>
                        <span className="text-xs text-gray-500">•</span>
                        <span className="text-xs font-medium text-amber-200/90" title="Pipeline agent">
                          agent: {log.agent_type}
                        </span>
                      </>
                    ) : null}
                    {typeof log.task_type === 'string' && log.task_type ? (
                      <>
                        <span className="text-xs text-gray-500">•</span>
                        <span className="text-xs text-cyan-200/80" title="Routing task type">
                          task: {log.task_type}
                        </span>
                      </>
                    ) : null}
                    {typeof log.model_role === 'string' && log.model_role ? (
                      <>
                        <span className="text-xs text-gray-500">•</span>
                        <span
                          className="text-[10px] uppercase px-1.5 py-0 rounded border border-violet-500/30 text-violet-200/90"
                          title="Heavy vs light model tier (from routing / provider config)"
                        >
                          {log.model_role}
                        </span>
                      </>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                    <span>
                      Latency:{' '}
                      <span className={log.latency_ms > 30000 ? 'text-red-400' : 'text-gray-300'}>
                        {log.latency_ms ? `${(log.latency_ms / 1000).toFixed(1)}s` : 'N/A'}
                      </span>
                    </span>
                    {typeof log.prompt_tokens === 'number' && typeof log.completion_tokens === 'number' ? (
                      <span title="Input / output tokens from API usage">
                        Tok in/out:{' '}
                        <span className="text-gray-300">
                          {log.prompt_tokens} / {log.completion_tokens}
                        </span>
                      </span>
                    ) : null}
                    {log.tokens_used ? (
                      <span>
                        Total tok: <span className="text-gray-300">{log.tokens_used}</span>
                      </span>
                    ) : null}
                    {typeof log.estimated_cost_usd === 'number' ? (
                      <span className="text-emerald-200/90">
                        ~${log.estimated_cost_usd.toFixed(4)}
                      </span>
                    ) : null}
                    {log.error && (
                      <span className="text-red-400 truncate max-w-[200px]" title={log.error}>
                        Error: {log.error}
                      </span>
                    )}
                  </div>
                  {/* Prompt/Response previews */}
                  <div className="mt-1.5 flex flex-col gap-1">
                    {log.prompt_preview && (
                      <details className="text-xs">
                        <summary className="text-gray-500 cursor-pointer hover:text-gray-300">
                          Prompt preview
                        </summary>
                        <pre className="mt-1 p-2 bg-black/30 rounded text-gray-400 whitespace-pre-wrap break-words max-h-24 overflow-y-auto">
                          {log.prompt_preview}
                        </pre>
                      </details>
                    )}
                    {log.response_preview && (
                      <details className="text-xs">
                        <summary className="text-gray-500 cursor-pointer hover:text-gray-300">
                          Response preview
                        </summary>
                        <pre className="mt-1 p-2 bg-black/30 rounded text-gray-400 whitespace-pre-wrap break-words max-h-24 overflow-y-auto">
                          {log.response_preview}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-gray-600 sm:whitespace-nowrap sm:pt-0.5 sm:text-right">
                  {llmLogTimeMs(log) > 0
                    ? new Date(llmLogTimeMs(log)).toLocaleTimeString()
                    : log.timestamp != null && log.timestamp !== ''
                      ? String(log.timestamp)
                      : ''}
                </span>
                </div>
              </div>
            ))}
            {hasMoreFromServer && (
              <div className="flex flex-col items-center gap-2 border-t border-white/10 py-4">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={loadingMore}
                  onClick={() => void loadMoreLogs()}
                  className="min-w-[12rem]"
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                      Loading…
                    </>
                  ) : (
                    <>Load more ({logs.length} / {totalRows})</>
                  )}
                </Button>
                <p className="text-[10px] text-gray-600 text-center max-w-md">
                  Older calls are fetched in chunks of {LLM_LOG_PAGE_SIZE}. Narrow provider or time range if the list is huge.
                </p>
              </div>
            )}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
