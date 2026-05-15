'use client';

import React, { useEffect, useState } from 'react';
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
import { readAdminMetricsCache, writeAdminMetricsCache } from '@/lib/adminMetricsCache';

export function DashboardTab() {
  /** Stale-while-revalidate: show last full snapshot immediately, then quick → full refresh. */
  const [data, setData] = useState<DashboardData | null>(() => readAdminMetricsCache());

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const quick = await api.getDashboard(true);
        if (!cancelled) {
          setData((prev) => {
            if (!prev) return quick;
            const qSf = quick.pipeline.storefront_visible_products;
            const pSf = prev.pipeline.storefront_visible_products;
            if ((qSf === null || qSf === undefined) && typeof pSf === 'number') {
              return {
                ...quick,
                pipeline: {
                  ...quick.pipeline,
                  storefront_visible_products: pSf,
                },
                dashboard_partial: false,
              };
            }
            return quick;
          });
        }
      } catch {
        /* keep cache / skeleton */
      }
      try {
        const full = await api.getDashboard(false);
        if (!cancelled) {
          setData(full);
          writeAdminMetricsCache(full);
        }
      } catch {
        /* quick or cache remains */
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="glass-card p-6">
            <div className="skeleton h-4 w-20 mb-3" />
            <div className="skeleton h-8 w-16 mb-2" />
            <div className="skeleton h-3 w-24" />
          </div>
        ))}
      </div>
    );
  }

  const total = data.pipeline.total_products;
  const completed = data.pipeline.completed_products;
  const sfRaw = data.pipeline.storefront_visible_products;
  const sfPending =
    Boolean(data.dashboard_partial) && (sfRaw === null || sfRaw === undefined);
  const storefront = sfRaw ?? 0;
  const failed = data.pipeline.failed_products;
  const active = data.pipeline.active_products;
  const completionRate = total > 0 ? ((completed / total) * 100) : 0;
  /** Share of shipped pipeline rows (COMPLETED / DEPLOYED_PRODUCTION) that list on the public grid. */
  const storefrontYieldPct =
    !sfPending && completed > 0 ? Math.round((storefront / completed) * 100) : null;

  const factoryHealthScore = (() => {
    const p = data.pipeline;
    const t = p.total_products || 0;
    if (t <= 0) return 100;
    const failedN = p.failed_products || 0;
    const timeouts = p.timed_out_tasks || 0;
    const pending = p.pending_tasks || 0;
    const running = p.running_tasks || 0;
    const failPen = Math.min(48, (failedN / t) * 60);
    const toPen = Math.min(22, timeouts * 4);
    const queuePen = Math.min(18, (pending + running) * 0.35);
    let score = 100 - failPen - toPen - queuePen;
    if (!sfPending && storefrontYieldPct != null) {
      score += Math.min(12, storefrontYieldPct / 10);
    }
    return Math.round(Math.max(0, Math.min(100, score)));
  })();

  const healthBand =
    factoryHealthScore >= 75 ? 'strong' : factoryHealthScore >= 50 ? 'fair' : 'needs attention';

  const stats = [
    {
      label: 'Total Products',
      value: total,
      icon: FileText,
      color: 'from-indigo-500 to-purple-500',
    },
    {
      label: 'Active Pipeline',
      value: active,
      icon: Activity,
      color: 'from-emerald-500 to-teal-500',
    },
    {
      label: 'Shipped builds',
      value: completed,
      icon: CheckCircle2,
      color: 'from-green-500 to-emerald-500',
    },
    {
      label: 'On storefront',
      value: sfPending ? null : storefront,
      icon: Store,
      color: 'from-cyan-500 to-sky-500',
    },
    {
      label: 'Needs rework',
      value: failed,
      icon: AlertTriangle,
      color: 'from-amber-500 to-orange-500',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
        {stats.map((stat, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <GlassCard>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-400 mb-1">{stat.label}</p>
                  <p className="text-3xl font-bold text-white">
                    {stat.value === null ? (
                      <span className="inline-flex items-center gap-2 text-gray-400 text-xl font-normal">
                        <Loader2 className="w-6 h-6 animate-spin shrink-0" aria-hidden />
                        …
                      </span>
                    ) : (
                      stat.value
                    )}
                  </p>
                </div>
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${stat.color} p-2`}>
                  <stat.icon className="w-full h-full text-white" />
                </div>
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <GlassCard className="border border-violet-500/25 bg-violet-500/[0.04]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Gauge className="h-5 w-5 text-violet-400" />
              Factory health score
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-400">
              Single 0–100 signal from existing dashboard metrics (failure load, timeouts, queue pressure, storefront
              yield). Not a replacement for per-product QA — a fast pulse for operators.
            </p>
          </div>
          <div className="text-right">
            <p className="text-4xl font-bold text-violet-200">{factoryHealthScore}</p>
            <p className="text-xs capitalize text-gray-500">{healthBand}</p>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar
            value={factoryHealthScore}
            label="Composite health"
            variant={factoryHealthScore >= 70 ? 'success' : factoryHealthScore >= 45 ? 'warning' : 'warning'}
          />
        </div>
      </GlassCard>

      {/* Primary ops KPI: pipeline completion alone is not “shipping”; storefront listing is. */}
      <GlassCard className="border border-cyan-500/25 bg-cyan-500/[0.04]">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
          <div>
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Store className="w-5 h-5 text-cyan-400" />
              North star — public storefront
            </h3>
            <p className="text-sm text-gray-400 mt-1 max-w-3xl">
              The factory’s operational goal is <strong className="text-gray-300">listed, buyer-visible products</strong>, not a counter of
              pipeline «completed». Completed builds that fail marketplace gates stay internal until rework or explicit admin override —
              use Pipeline → storefront controls to track intent (planned rework / abandon / force-list).
            </p>
          </div>
          {sfPending ? (
            <div className="text-right shrink-0 flex items-center justify-end gap-2 text-gray-400 text-sm">
              <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
              <span>Storefront count…</span>
            </div>
          ) : (
            storefrontYieldPct !== null && (
              <div className="text-right shrink-0">
                <p className="text-3xl font-bold text-cyan-300">{storefrontYieldPct}%</p>
                <p className="text-xs text-gray-500">listed ÷ shipped builds</p>
              </div>
            )
          )}
        </div>
        {sfPending ? (
          <p className="text-sm text-gray-500 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
            Loading public storefront totals (cached scan, short wait)…
          </p>
        ) : storefrontYieldPct !== null ? (
          <>
            <ProgressBar value={storefrontYieldPct} label="Shipped builds → storefront conversion" variant="success" />
            <p className="text-xs text-gray-500 mt-2">
              {storefront} listed on the public grid · {completed} products in completed pipeline state (approximation; excludes deployed-only SKUs from denominator).
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-500">No completed products yet — this KPI activates once builds reach completed.</p>
        )}
      </GlassCard>

      {/* Pipeline Metrics */}
      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Pipeline Metrics</h3>
          <div className="space-y-4">
            <ProgressBar
              value={Math.round(completionRate)}
              label="Completion Rate"
              variant="success"
            />
            <div className="flex justify-between text-sm text-gray-400">
              <span>Pending Tasks</span>
              <span className="text-white font-medium">{data.pipeline.pending_tasks}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Running Tasks</span>
              <span className="text-white font-medium">{data.pipeline.running_tasks}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Timed Out Tasks</span>
              <span className="text-white font-medium">{data.pipeline.timed_out_tasks}</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">System Resources</h3>
          <div className="space-y-4">
            <ProgressBar
              value={data.resources.cpu_percent}
              label="CPU"
              variant={data.resources.cpu_percent > 80 ? 'warning' : 'primary'}
            />
            <ProgressBar
              value={data.resources.memory_percent}
              label="Memory"
              variant={data.resources.memory_percent > 80 ? 'warning' : 'primary'}
            />
            <ProgressBar
              value={data.resources.disk_percent}
              label="Disk"
              variant={data.resources.disk_percent > 80 ? 'warning' : 'primary'}
            />
          </div>
        </GlassCard>
      </div>

      {/* Revenue & Security */}
      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <div className="flex items-center gap-3 mb-4">
            <DollarSign className="w-5 h-5 text-emerald-400" />
            <h3 className="text-lg font-semibold text-white">Revenue</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 24h</span>
              <span className="text-white font-medium">${data.revenue.last_24h.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 7 Days</span>
              <span className="text-white font-medium">${data.revenue.last_7d.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 30 Days</span>
              <span className="text-white font-medium">${data.revenue.last_30d.toFixed(2)}</span>
            </div>
            {data.revenue.total_approx_usd != null && (
              <div className="flex justify-between text-sm border-t border-white/10 pt-2">
                <span className="text-gray-400">All-time (approx. USD, incl. ETH/SOL est.)</span>
                <span className="text-white font-medium">${data.revenue.total_approx_usd.toFixed(2)}</span>
              </div>
            )}
            {data.revenue.orders_completed != null && (
              <div className="flex justify-between text-xs text-gray-500 pt-1">
                <span>Paid orders</span>
                <span>{data.revenue.orders_completed}</span>
              </div>
            )}
            {data.revenue.payments_pending != null && data.revenue.payments_pending > 0 && (
              <div className="flex justify-between text-xs text-amber-400/90 pt-1">
                <span>Pending checkout</span>
                <span>{data.revenue.payments_pending}</span>
              </div>
            )}
          </div>
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-3 mb-4">
            <Shield className="w-5 h-5 text-indigo-400" />
            <h3 className="text-lg font-semibold text-white">Security</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Status</span>
              <span className="text-white font-medium capitalize">{data.security.status}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Failed Logins (15m)</span>
              <span className="text-white font-medium">{data.security.failed_logins_15min}</span>
            </div>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
