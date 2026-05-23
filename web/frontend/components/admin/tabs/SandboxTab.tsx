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
import { launchSandboxWithProgress } from '@/lib/sandboxLaunch';
import { SandboxLaunchOverlay } from '@/components/SandboxLaunchOverlay';
import { sandboxLaunchLabel } from '@/lib/sandboxLaunchI18n';

export function SandboxTab({ locale }: { locale: AdminLocale }) {
  const [products, setProducts] = useState<any[]>([]);
  const [activeSandboxes, setActiveSandboxes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [gitStatuses, setGitStatuses] = useState<Record<string, any>>({});
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);
  const [remoteUrls, setRemoteUrls] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [sandboxLaunchProgress, setSandboxLaunchProgress] = useState<{
    percent: number;
    label: string;
  } | null>(null);

  const loadData = async () => {
    try {
      const [prodResult, sandboxResult] = await Promise.all([
        api.listSandboxableProducts(),
        api.listActiveSandboxes(),
      ]);
      setProducts(prodResult.products || []);
      setActiveSandboxes(sandboxResult.sandboxes || []);
    } catch (err) {
      console.error('Failed to load sandbox data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const loadGitStatus = async (productId: string) => {
    try {
      const status = await api.gitStatus(productId);
      setGitStatuses((prev) => ({ ...prev, [productId]: status }));
    } catch {
      showMessage('error', `Failed to load git status for ${productId}`);
    }
  };

  const handleInitGit = async (productId: string) => {
    setActionLoading(`init-${productId}`);
    try {
      const remoteUrl = remoteUrls[productId] || '';
      const result = await api.gitInit(productId, remoteUrl || undefined);
      showMessage('success', `Git ${result.status} for ${productId}`);
      await loadGitStatus(productId);
      await loadData();
    } catch (err: any) {
      showMessage('error', err?.message || 'Git init failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePush = async (productId: string) => {
    setActionLoading(`push-${productId}`);
    try {
      const result = await api.gitPush(productId);
      showMessage('success', `Pushed ${productId} to ${result.remote}/${result.branch}`);
    } catch (err: any) {
      showMessage('error', err?.message || 'Git push failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStartSandbox = async (productId: string) => {
    setActionLoading(`start-${productId}`);
    setSandboxLaunchProgress({ percent: 5, label: sandboxLaunchLabel(locale, 'starting') });
    try {
      const result = await launchSandboxWithProgress(
        productId,
        { locale },
        setSandboxLaunchProgress,
      );
      showMessage('success', `Sandbox ${result.sandbox_id} started`);
      window.location.href = result.url;
    } catch (err: unknown) {
      const msg =
        err instanceof Error && /invalid or expired token/i.test(err.message)
          ? 'Session expired — sign in again at Admin → Login, then retry.'
          : err instanceof Error
            ? err.message
            : 'Failed to start sandbox';
      showMessage('error', msg);
    } finally {
      setActionLoading(null);
      setSandboxLaunchProgress(null);
    }
  };

  const handleStopSandbox = async (sandboxId: string) => {
    setActionLoading(`stop-${sandboxId}`);
    try {
      await api.stopSandbox(sandboxId);
      showMessage('success', `Sandbox ${sandboxId} stopped`);
      await loadData();
    } catch (err: any) {
      showMessage('error', err?.message || 'Failed to stop sandbox');
    } finally {
      setActionLoading(null);
    }
  };

  const toggleExpand = (productId: string) => {
    if (expandedProduct === productId) {
      setExpandedProduct(null);
    } else {
      setExpandedProduct(productId);
      if (!gitStatuses[productId]) {
        loadGitStatus(productId);
      }
    }
  };

  const activeProductIds = activeSandboxes.map((sb: any) => sb.product_id);

  if (loading) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-white mb-4">{t(locale, 'sandbox.title')}</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card p-6">
              <div className="skeleton h-4 w-20 mb-3" />
              <div className="skeleton h-3 w-32 mb-2" />
              <div className="skeleton h-8 w-24 mt-4" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SandboxLaunchOverlay
        open={sandboxLaunchProgress !== null}
        progress={sandboxLaunchProgress}
        locale={locale}
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold text-white">{t(locale, 'sandbox.title')}</h2>
        <Button variant="secondary" size="sm" onClick={loadData} className="w-full shrink-0 sm:w-auto">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      {/* Status message toast */}
      {message && (
        <div className={`px-4 py-3 rounded-xl text-sm ${
          message.type === 'success'
            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
            : 'bg-red-500/20 text-red-300 border border-red-500/30'
        }`}>
          {message.type === 'success' ? <CheckCircle2 className="w-4 h-4 inline mr-2" /> : <AlertTriangle className="w-4 h-4 inline mr-2" />}
          {message.text}
        </div>
      )}

      {/* Active Sandboxes Summary */}
      <GlassCard>
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-lg font-semibold text-white">Active Sandboxes</h3>
          <Badge variant={activeSandboxes.length > 0 ? 'success' : 'info'} className="w-fit">
            {activeSandboxes.length} running
          </Badge>
        </div>
        {activeSandboxes.length === 0 ? (
          <p className="text-sm text-gray-500">No active sandboxes. Start one from a product card below.</p>
        ) : (
          <div className="space-y-2">
            {activeSandboxes.map((sb: any) => (
              <div key={sb.id} className="flex flex-col gap-3 p-3 bg-white/5 rounded-xl sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="w-2 h-2 shrink-0 rounded-full bg-emerald-400 animate-pulse" />
                  <div className="min-w-0">
                    <p className="text-sm text-white font-medium break-all">{sb.product_id}</p>
                    <p className="text-xs text-gray-500 break-all">ID: {sb.id}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      window.location.href = `/api/sandbox/view/${sb.id}`;
                    }}
                  >
                    <ExternalLink className="w-3 h-3 mr-1" /> View
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleStopSandbox(sb.id)}
                    disabled={actionLoading === `stop-${sb.id}`}
                  >
                    {actionLoading === `stop-${sb.id}` ? 'Stopping...' : 'Stop'}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Product Code Directories */}
      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Product Code Directories</h3>
        {products.length === 0 ? (
          <div className="text-center py-8">
            <Terminal className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">No product code directories found.</p>
            <p className="text-xs text-gray-600 mt-1">
              Products will appear here once the pipeline generates code.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {products.map((product: any) => (
              <div key={product.product_id} className="border border-white/5 rounded-xl overflow-hidden">
                {/* Product header */}
                <div className="flex flex-col gap-3 p-4 hover:bg-white/5 transition-colors cursor-pointer sm:flex-row sm:items-center sm:justify-between"
                     onClick={() => toggleExpand(product.product_id)}>
                  <div className="flex min-w-0 items-center gap-3">
                    <ChevronRight className={`w-4 h-4 shrink-0 text-gray-500 transition-transform ${
                      expandedProduct === product.product_id ? 'rotate-90' : ''
                    }`} />
                    <div className="min-w-0">
                      <p className="text-sm text-white font-medium">{product.product_name || product.product_id}</p>
                      <p className="text-xs text-gray-500 break-all">{product.product_id} · {product.code_dir}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    <Badge variant={product.git_status === 'initialized' ? 'success' : 'info'}>
                      {product.git_status === 'initialized' ? 'git' : 'no git'}
                    </Badge>
                    {activeProductIds.includes(product.product_id) && (
                      <Badge variant="success">sandbox</Badge>
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {expandedProduct === product.product_id && (
                  <div className="border-t border-white/5 p-4 space-y-3 bg-white/[0.02]">
                    {/* Git status */}
                    {gitStatuses[product.product_id] ? (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Git Status</p>
                        <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
                          <div className="bg-white/5 rounded-lg p-2">
                            <span className="text-gray-500">Branch:</span>{' '}
                            <span className="text-white">{gitStatuses[product.product_id].branch || 'N/A'}</span>
                          </div>
                          <div className="bg-white/5 rounded-lg p-2">
                            <span className="text-gray-500">Status:</span>{' '}
                            <span className="text-white">{gitStatuses[product.product_id].status || 'N/A'}</span>
                          </div>
                          <div className="bg-white/5 rounded-lg p-2">
                            <span className="text-gray-500">Uncommitted:</span>{' '}
                            <span className="text-white">{gitStatuses[product.product_id].uncommitted_changes || 0}</span>
                          </div>
                          <div className="bg-white/5 rounded-lg p-2">
                            <span className="text-gray-500">Remotes:</span>{' '}
                            <span className="text-white">{gitStatuses[product.product_id].remotes?.length || 0}</span>
                          </div>
                        </div>

                        {/* Recent commits */}
                        {gitStatuses[product.product_id].recent_commits?.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mt-3 mb-1">Recent Commits</p>
                            <div className="space-y-1">
                              {gitStatuses[product.product_id].recent_commits.map((commit: string, ci: number) => (
                                <div key={ci} className="text-xs text-gray-400 font-mono bg-white/5 rounded px-2 py-1">
                                  {commit}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Uncommitted changes */}
                        {gitStatuses[product.product_id].change_list?.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mt-3 mb-1">Pending Changes</p>
                            <div className="space-y-1 max-h-32 overflow-y-auto">
                              {gitStatuses[product.product_id].change_list.map((change: string, ci: number) => (
                                <div key={ci} className="text-xs text-gray-400 font-mono bg-white/5 rounded px-2 py-1">
                                  {change}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-3">
                        <p className="text-xs text-gray-500">Click "Load Status" to view git details</p>
                      </div>
                    )}

                    {/* Remote URL input */}
                    {product.git_status !== 'initialized' && (
                      <div className="flex items-center gap-2">
                        <Input
                          placeholder="Git remote URL (optional)"
                          value={remoteUrls[product.product_id] || ''}
                          onChange={(e) => setRemoteUrls((prev) => ({ ...prev, [product.product_id]: e.target.value }))}
                          className="text-xs"
                        />
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="flex flex-wrap gap-2 pt-2">
                      {product.git_status !== 'initialized' ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleInitGit(product.product_id)}
                          disabled={actionLoading === `init-${product.product_id}`}
                        >
                          {actionLoading === `init-${product.product_id}` ? 'Initializing...' : 'Init Git'}
                        </Button>
                      ) : (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => loadGitStatus(product.product_id)}
                            disabled={actionLoading === `status-${product.product_id}`}
                          >
                            <RefreshCw className="w-3 h-3 mr-1" /> Refresh Status
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handlePush(product.product_id)}
                            disabled={actionLoading === `push-${product.product_id}`}
                          >
                            {actionLoading === `push-${product.product_id}` ? 'Pushing...' : 'Push'}
                          </Button>
                        </>
                      )}
                      <Button
                        variant={activeProductIds.includes(product.product_id) ? 'secondary' : 'primary'}
                        size="sm"
                        onClick={() =>
                          activeProductIds.includes(product.product_id)
                            ? handleStopSandbox(
                                activeSandboxes.find((sb: any) => sb.product_id === product.product_id)?.id
                              )
                            : handleStartSandbox(product.product_id)
                        }
                        disabled={
                          actionLoading === `start-${product.product_id}` ||
                          actionLoading === `stop-${activeSandboxes.find((sb: any) => sb.product_id === product.product_id)?.id}`
                        }
                      >
                        {activeProductIds.includes(product.product_id) ? 'Stop Sandbox' : 'Start Sandbox'}
                      </Button>
                    </div>
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
