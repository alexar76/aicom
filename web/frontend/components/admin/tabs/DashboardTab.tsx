'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  DollarSign,
  FileText,
  Gauge,
  Loader2,
  Shield,
  Store,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { ProgressBar } from '@/components/ui/ProgressBar';
import api, { type DashboardData } from '@/lib/api';
import {
  createEmptyDashboardData,
  mergeDashboardQuick,
  readAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';
import { prefetchAdminDashboard } from '@/lib/prefetchAdminDashboard';

function bootDashboardData(): DashboardData {
  return readAdminMetricsCache() ?? createEmptyDashboardData();
}

export function DashboardTab() {
  const [data, setData] = useState<DashboardData>(bootDashboardData);
  const [refreshing, setRefreshing] = useState(true);
  const hadCacheOnMount = useState(() => readAdminMetricsCache() != null)[0];

  useEffect(() => {
    let cancelled = false;
    prefetchAdminDashboard();

    const run = async () => {
      try {
        const quick = await api.getDashboard(true);
        if (!cancelled) {
          setData((prev) => mergeDashboardQuick(prev, quick));
        }
      } catch {
        /* keep cache / zeros */
      }
      try {
        const full = await api.getDashboard(false);
        if (!cancelled) {
          setData(full);
          writeAdminMetricsCache(full);
        }
      } catch {
        /* quick or cache remains */
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const total = data.pipeline.total_products;
  const completed = data.pipeline.completed_products;
  const sfRaw = data.pipeline.storefront_visible_products;
  const sfPending =
    Boolean(data.dashboard_partial) && (sfRaw === null || sfRaw === undefined);
  const storefront = sfRaw ?? 0;
  const failed = data.pipeline.failed_products;
  const active = data.pipeline.active_products;
  const completionRate = total > 0 ? (completed / total) * 100 : 0;
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

  const failedAlerts = data.pipeline.failed_alerts ?? [];

  return (
    <motion.div className="space-y-8">
      {refreshing ? (
        <p className="flex items-center gap-2 text-xs text-gray-500" aria-live="polite">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
          {hadCacheOnMount ? 'Refreshing metrics…' : 'Loading live metrics…'}
        </p>
      ) : null}

      {(failed > 0 || failedAlerts.length > 0) && (
        <motion.div
          role="alert"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border-2 border-red-500/50 bg-gradient-to-br from-red-950/90 via-red-900/40 to-amber-950/30 p-5 shadow-lg shadow-red-900/25"
        >
          <motion.div className="flex items-start gap-3 mb-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-500/30 border border-red-400/50">
              <AlertTriangle className="h-7 w-7 text-red-200" aria-hidden />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-red-50">
                {failed} product{failed === 1 ? '' : 's'} need rework (FAILED)
              </h2>
              <p className="text-sm text-red-100/90 mt-1 max-w-3xl">
                Pipeline paused — not deleted. Open Pipeline and use Send to rework. A Telegram
                alert is sent when a product fails (if enabled in Settings).
              </p>
            </div>
          </motion.div>
          <ul className="space-y-3">
            {(failedAlerts.length > 0
              ? failedAlerts
              : [{ product_id: '—', title: 'Failed products', cause_plain: 'Open Pipeline tab for details.' }]
            ).map((item) => (
              <li
                key={item.product_id}
                className="rounded-xl border border-red-500/25 bg-black/25 px-4 py-3"
              >
                <p className="text-sm font-medium text-red-50 font-mono">{item.product_id}</p>
                {item.title && item.title !== item.product_id ? (
                  <p className="text-xs text-red-200/80 mt-0.5 truncate">{item.title}</p>
                ) : null}
                {item.headline ? (
                  <p className="text-xs uppercase tracking-wide text-red-300/90 mt-2">{item.headline}</p>
                ) : null}
                <p className="text-sm text-red-100/95 mt-1 leading-relaxed">
                  {item.cause_plain || item.failure_reason || 'No failure reason stored.'}
                </p>
                {item.failed_agent ? (
                  <p className="text-[11px] text-red-200/60 mt-1">Agent: {item.failed_agent}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </motion.div>
      )}


      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <GlassCard>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-400 mb-1">{stat.label}</p>
                  <p className="text-3xl font-bold text-white tabular-nums">
                    {stat.value === null ? (
                      <span className="inline-flex items-center gap-2 text-gray-400 text-xl font-normal">
                        <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
                        …
                      </span>
                    ) : (
                      stat.value
                    )}
                  </p>
                </div>
                <motion.div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${stat.color} p-2`}>
                  <stat.icon className="w-full h-full text-white" />
                </motion.div>
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <GlassCard className="border border-violet-500/25 bg-violet-500/[0.04]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold leading-normal text-white">
              <span
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center text-violet-400"
                aria-hidden
              >
                <Gauge className="h-5 w-5" strokeWidth={2} />
              </span>
              Factory health score
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-400">
              Single 0–100 signal from existing dashboard metrics (failure load, timeouts, queue pressure,
              storefront yield).
            </p>
          </div>
          <div className="text-right">
            <p className="text-4xl font-bold text-violet-200 tabular-nums">{factoryHealthScore}</p>
            <p className="text-xs capitalize text-gray-500">{healthBand}</p>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar
            value={factoryHealthScore}
            label="Composite health"
            variant={factoryHealthScore >= 70 ? 'success' : 'warning'}
          />
        </div>
      </GlassCard>

      <GlassCard className="border border-cyan-500/25 bg-cyan-500/[0.04]">
        <motion.div className="flex flex-wrap items-start justify-between gap-4 mb-3">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold leading-normal text-white">
              <span
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center text-cyan-400"
                aria-hidden
              >
                <Store className="h-5 w-5" strokeWidth={2} />
              </span>
              North star — public storefront
            </h3>
            <p className="text-sm text-gray-400 mt-1 max-w-3xl">
              The factory’s operational goal is listed, buyer-visible products, not pipeline «completed»
              alone.
            </p>
          </div>
          {sfPending ? (
            <div className="text-right shrink-0 flex items-center justify-end gap-2 text-gray-400 text-sm">
              <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
              <span>Storefront count…</span>
            </div>
          ) : storefrontYieldPct !== null ? (
            <div className="text-right shrink-0">
              <p className="text-3xl font-bold text-cyan-300 tabular-nums">{storefrontYieldPct}%</p>
              <p className="text-xs text-gray-500">listed ÷ shipped builds</p>
            </div>
          ) : null}
        </motion.div>
        {sfPending ? (
          <p className="text-sm text-gray-500 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
            Loading public storefront totals…
          </p>
        ) : storefrontYieldPct !== null ? (
          <>
            <ProgressBar value={storefrontYieldPct} label="Shipped builds → storefront conversion" variant="success" />
            <p className="text-xs text-gray-500 mt-2 tabular-nums">
              {storefront} listed · {completed} completed pipeline rows
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-500">No completed products yet.</p>
        )}
      </GlassCard>

      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Pipeline Metrics</h3>
          <div className="space-y-4">
            <ProgressBar value={Math.round(completionRate)} label="Completion Rate" variant="success" />
            <div className="flex justify-between text-sm text-gray-400">
              <span>Pending Tasks</span>
              <span className="text-white font-medium tabular-nums">{data.pipeline.pending_tasks}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Running Tasks</span>
              <span className="text-white font-medium tabular-nums">{data.pipeline.running_tasks}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Timed Out Tasks</span>
              <span className="text-white font-medium tabular-nums">{data.pipeline.timed_out_tasks}</span>
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

      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <div className="flex items-center gap-3 mb-4">
            <DollarSign className="w-5 h-5 text-emerald-400" />
            <h3 className="text-lg font-semibold text-white">Revenue</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 24h</span>
              <span className="text-white font-medium tabular-nums">${data.revenue.last_24h.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 7 Days</span>
              <span className="text-white font-medium tabular-nums">${data.revenue.last_7d.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Last 30 Days</span>
              <span className="text-white font-medium tabular-nums">${data.revenue.last_30d.toFixed(2)}</span>
            </div>
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
              <span className="text-white font-medium tabular-nums">{data.security.failed_logins_15min}</span>
            </div>
          </div>
        </GlassCard>
      </div>
    </motion.div>
  );
}
