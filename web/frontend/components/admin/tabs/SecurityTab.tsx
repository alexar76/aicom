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
import { fetchPipelineCatalogAllPages } from '@/lib/pipelineCatalogFetch';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme, parseDatetimeLocalToUnixSeconds } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';

function auditEntryTimestampSeconds(log: Record<string, unknown>): number {
  const t = log?.timestamp;
  if (t == null) return 0;
  const n = typeof t === 'number' ? t : Number(t);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n > 1e12 ? n / 1000 : n;
}

export function SecurityTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);
  const [securityReport, setSecurityReport] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [auditSearch, setAuditSearch] = useState('');
  const [auditSeverityFilter, setAuditSeverityFilter] = useState('all');
  const [auditDateFrom, setAuditDateFrom] = useState('');
  const [auditDateTo, setAuditDateTo] = useState('');
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditLoadError, setAuditLoadError] = useState(false);
  const [auditTotal, setAuditTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setProducts([]);
    setCatalogError(false);
    setCatalogLoading(true);
    fetchPipelineCatalogAllPages('shipped_first', {
      onPage: ({ batch }) => {
        if (cancelled) return;
        setProducts((prev) => [...prev, ...batch]);
        setCatalogLoading(false);
      },
    })
      .then(() => {
        if (cancelled) return;
        setCatalogLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setCatalogError(true);
        setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const since = parseDatetimeLocalToUnixSeconds(auditDateFrom);
    const until = parseDatetimeLocalToUnixSeconds(auditDateTo);
    setAuditLoadError(false);
    setAuditLoading(true);
    api
      .getSecurityLogs(2000, since, until)
      .then((res) => {
        setLogs(res.logs || []);
        setAuditTotal(typeof res.total === 'number' ? res.total : res.logs?.length || 0);
      })
      .catch(() => {
        setLogs([]);
        setAuditTotal(0);
        setAuditLoadError(true);
      })
      .finally(() => {
        setAuditLoading(false);
      });
  }, [auditDateFrom, auditDateTo]);

  const loadSecurityReport = async (productId: string) => {
    setSelectedProduct(productId);
    setReportLoading(true);
    setSecurityReport(null);
    try {
      const data = await api.getSecurityReport(productId);
      setSecurityReport(data.report);
    } catch {
      setSecurityReport(null);
    } finally {
      setReportLoading(false);
    }
  };

  const filteredProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    if (!q) return products;
    return products.filter((p: any) => {
      const idea = String(p?.idea || '').toLowerCase();
      const id = String(p?.id || '').toLowerCase();
      const st = String(p?.state || '').toLowerCase();
      return idea.includes(q) || id.includes(q) || st.includes(q);
    });
  }, [products, productSearch]);

  const auditSeverities = useMemo(() => {
    const s = new Set<string>();
    for (const l of logs) {
      const sev = String(l?.severity || '').toLowerCase();
      if (sev) s.add(sev);
    }
    return Array.from(s).sort();
  }, [logs]);

  const filteredLogs = useMemo(() => {
    const q = auditSearch.trim().toLowerCase();
    return logs.filter((log: any) => {
      const sev = String(log?.severity || '').toLowerCase();
      if (auditSeverityFilter !== 'all' && sev !== auditSeverityFilter) return false;
      if (!q) return true;
      const action = String(log?.action || '').toLowerCase();
      const actor = String(log?.actor || '').toLowerCase();
      const resource = String(log?.resource || '').toLowerCase();
      return action.includes(q) || actor.includes(q) || resource.includes(q) || sev.includes(q);
    });
  }, [logs, auditSearch, auditSeverityFilter]);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white mb-4">Security</h2>

      {/* Security Reports from Pipeline */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">Security Reports</h3>
        {catalogLoading && products.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-gray-400">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
            <p className="text-sm">Loading pipeline catalog…</p>
            <p className="text-xs text-gray-500 max-w-md text-center">
              The admin API may retry on cold start or busy workers — this can take a short while before the first page arrives.
            </p>
          </div>
        ) : catalogError ? (
          <div className="text-center py-8">
            <AlertTriangle className="w-12 h-12 text-amber-500/80 mx-auto mb-3" aria-hidden />
            <p className="text-gray-300">Could not load pipeline products.</p>
            <p className="text-xs text-gray-500 mt-2 max-w-md mx-auto">
              Check network, admin session, and backend logs. Refresh the page to try again.
            </p>
          </div>
        ) : products.length === 0 ? (
          <div className="text-center py-8">
            <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No pipeline products in the catalog.</p>
            <p className="text-xs text-gray-600 mt-2 max-w-md mx-auto">
              With SQLite enabled, the list comes from the database. Security agent reports appear here only for products that have completed the Security stage (after QA). If the pipeline is empty or nothing has reached Security yet, this list stays empty.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="mb-2">
              <Input
                value={productSearch}
                onChange={(e) => setProductSearch(e.target.value)}
                placeholder="Search products by id, idea, state..."
              />
              <p className="text-[11px] text-gray-500 mt-1">
                Showing {filteredProducts.length} of {products.length}
              </p>
              <button
                type="button"
                onClick={() => setProductSearch('')}
                className="text-[11px] text-indigo-300 hover:text-indigo-200 underline underline-offset-2 mt-1"
              >
                Reset product search
              </button>
            </div>
            {filteredProducts.map((p: any) => (
              <div key={p.id}>
                <button
                  onClick={() => loadSecurityReport(p.id)}
                  className={`w-full text-left p-3 rounded-xl transition-colors ${
                    selectedProduct === p.id
                      ? 'bg-indigo-500/10 border border-indigo-500/30'
                      : 'bg-white/5 hover:bg-white/10 border border-transparent'
                  }`}
                >
                  <p className="text-sm text-white font-medium">{p.idea || p.id}</p>
                  <p className="text-xs text-gray-500 mt-1">ID: {p.id}</p>
                </button>

                {/* Show report for selected product */}
                {selectedProduct === p.id && (
                  <div className="mt-3 pl-4 border-l-2 border-indigo-500/30">
                    {reportLoading ? (
                      <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
                        <span className="w-4 h-4 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
                        Loading security report...
                      </div>
                    ) : securityReport ? (
                      <div className="space-y-3">
                        {/* Score */}
                        {securityReport.security_score !== undefined && (
                          <div className="flex items-center gap-3">
                            <span className="text-sm text-gray-400">Security Score:</span>
                            <span className={`text-lg font-bold ${
                              securityReport.security_score >= 80 ? 'text-emerald-400' :
                              securityReport.security_score >= 60 ? 'text-yellow-400' :
                              'text-red-400'
                            }`}>
                              {securityReport.security_score}/100
                            </span>
                            {securityReport.grade && (
                              <Badge variant={
                                securityReport.grade === 'A' ? 'success' :
                                securityReport.grade === 'B' ? 'success' :
                                securityReport.grade === 'C' ? 'warning' : 'error'
                              }>
                                Grade {securityReport.grade}
                              </Badge>
                            )}
                          </div>
                        )}

                        {/* Vulnerabilities summary */}
                        {(securityReport.vulnerabilities?.length > 0 || securityReport.findings?.length > 0) && (
                          <div>
                            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                              Findings ({securityReport.vulnerabilities?.length || securityReport.findings?.length})
                            </p>
                            <div className="space-y-2 max-h-60 overflow-y-auto">
                              {(securityReport.vulnerabilities || securityReport.findings || []).slice(0, 20).map((v: any, vi: number) => (
                                <div key={vi} className="text-xs bg-white/5 rounded-lg p-3 border border-white/5">
                                  <div className="flex items-center gap-2 mb-1">
                                    <Badge variant={
                                      v.severity === 'critical' || v.severity === 'high' ? 'error' :
                                      v.severity === 'medium' ? 'warning' : 'info'
                                    }>
                                      {v.severity || 'info'}
                                    </Badge>
                                    <span className="text-white font-medium">{v.category || v.type || 'Finding'}</span>
                                  </div>
                                  {v.file && <p className="text-gray-500 mt-1">File: {v.file}</p>}
                                  {v.description && <p className="text-gray-400 mt-1">{v.description}</p>}
                                  {v.recommendation && (
                                    <p className="text-emerald-400/80 mt-1">
                                      Fix: {v.recommendation}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Raw report fallback */}
                        {!securityReport.vulnerabilities && !securityReport.findings && (
                          <pre className="text-xs text-gray-400 bg-white/5 rounded-lg p-3 max-h-60 overflow-auto whitespace-pre-wrap font-mono">
                            {JSON.stringify(securityReport, null, 2)}
                          </pre>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 py-3">No security report found for this product.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Audit Logs */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">Security Audit Logs</h3>
        <p className="text-xs text-gray-500 mb-4">
          Admin authentication and sensitive-action audit trail (not the pipeline Security agent). Appears after logins and admin API actions are recorded.
        </p>
        {auditLoading && logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-gray-400">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
            <p className="text-sm">Loading audit logs…</p>
          </div>
        ) : auditLoadError && logs.length === 0 ? (
          <div className="text-center py-8">
            <AlertTriangle className="w-12 h-12 text-amber-500/80 mx-auto mb-3" aria-hidden />
            <p className="text-gray-300">Could not load audit logs.</p>
            <p className="text-xs text-gray-500 mt-2 max-w-md mx-auto">Check network or admin session and try again.</p>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-8">
            <Shield className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No audit entries in this time window.</p>
            <p className="text-xs text-gray-600 mt-2 max-w-md mx-auto">
              Entries are written when admins sign in and when sensitive admin APIs are audited to disk. A fresh install or no admin activity yet is normal.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {auditLoadError && (
              <p className="text-xs text-amber-300/90">Partial or stale view — last load failed. Change filters or refresh.</p>
            )}
            <FilterControlsPanel
              onReset={() => {
                setAuditSearch('');
                setAuditSeverityFilter('all');
                setAuditDateFrom('');
                setAuditDateTo('');
              }}
              resetLabel="Reset audit filters"
              summary={`Showing ${filteredLogs.length} of ${logs.length} loaded (${auditTotal} in time window before cap)`}
              gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-2"
            >
              <Input
                value={auditSearch}
                onChange={(e) => setAuditSearch(e.target.value)}
                placeholder="Search action, actor, resource..."
              />
              <FilterSelect
                value={auditSeverityFilter}
                onChange={(e) => setAuditSeverityFilter(e.target.value)}
              >
                <option value="all">All severities</option>
                {auditSeverities.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </FilterSelect>
              <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
                <span>From (local)</span>
                <input
                  type="datetime-local"
                  value={auditDateFrom}
                  onChange={(e) => setAuditDateFrom(e.target.value)}
                  className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
                />
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-gray-500">
                <span>To (local)</span>
                <input
                  type="datetime-local"
                  value={auditDateTo}
                  onChange={(e) => setAuditDateTo(e.target.value)}
                  className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
                />
              </label>
            </FilterControlsPanel>
            {filteredLogs.map((log, i) => (
              <div
                key={i}
                className="flex flex-col gap-2 border-b border-white/5 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between sm:py-2"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <Badge
                    variant={
                      log.severity === 'critical' || log.severity === 'error'
                        ? 'error'
                        : log.severity === 'warning'
                        ? 'warning'
                        : 'info'
                    }
                  >
                    {log.severity}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-sm text-gray-300">{log.action}</p>
                    <p className="text-xs text-gray-500 break-all">{log.actor} • {log.resource}</p>
                  </div>
                </div>
                <span className="shrink-0 text-xs text-gray-500 sm:text-right">
                  {formatRelativeTime(auditEntryTimestampSeconds(log))}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
