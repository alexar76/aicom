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

export function SecurityTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);
  const [securityReport, setSecurityReport] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [auditSearch, setAuditSearch] = useState('');
  const [auditSeverityFilter, setAuditSeverityFilter] = useState('all');

  useEffect(() => {
    api.getSecurityLogs(20).then(setLogs).catch(() => {});
    api.getPipelineProducts(1000, 0).then((data) => {
      setProducts(data.products || []);
    }).catch(() => {});
  }, []);

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
        {products.length === 0 ? (
          <div className="text-center py-8">
            <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No pipeline products loaded.</p>
            <p className="text-xs text-gray-600 mt-2 max-w-md mx-auto">
              With SQLite enabled, the product list comes from the database. Security scans appear here only after a product completes the Security stage (after QA passes).
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
        {logs.length === 0 ? (
          <div className="text-center py-8">
            <Shield className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No audit entries yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            <FilterControlsPanel
              onReset={() => {
                setAuditSearch('');
                setAuditSeverityFilter('all');
              }}
              resetLabel="Reset audit filters"
              summary={`Showing ${filteredLogs.length} of ${logs.length}`}
              gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2"
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
                  {formatRelativeTime(log.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
