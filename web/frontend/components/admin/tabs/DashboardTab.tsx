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
  applyPublicStorefrontCount,
  createEmptyDashboardData,
  isPipelineMetricsReady,
  mergeDashboardQuick,
  readAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';
import { prefetchAdminDashboard } from '@/lib/prefetchAdminDashboard';
import { fetchPublicStorefrontListableCount } from '@/lib/refreshStorefrontListableCount';
import { CostOutcomeHeatmap } from '@/components/admin/tabs/CostOutcomeHeatmap';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

function bootDashboardData(): DashboardData {
  return readAdminMetricsCache() ?? createEmptyDashboardData();
}

export function DashboardTab({ locale }: { locale: AdminLocale }) {
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
      }
      try {
        const vitrine = await fetchPublicStorefrontListableCount();
        if (!cancelled && vitrine !== null) {
          setData((prev) => applyPublicStorefrontCount(prev, vitrine));
        }
      } catch {
        /* keep dashboard payload */
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const pipelineReady = isPipelineMetricsReady(data);
  const total = data.pipeline.total_products;
  const completed = data.pipeline.completed_products;
  const sfRaw = data.pipeline.storefront_visible_products;
  const sfPending =
    Boolean(data.dashboard_partial) && (sfRaw === null || sfRaw === undefined);
  const storefront = sfRaw ?? 0;
  const failed = data.pipeline.failed_products;
  const active = data.pipeline.active_products;
  const completionRate = pipelineReady && total > 0 ? (completed / total) * 100 : 0;
  const storefrontYieldPct =
    pipelineReady && !sfPending && completed > 0
      ? Math.round((storefront / completed) * 100)
      : null;

  const factoryHealthScore = ((): number | null => {
    if (!pipelineReady) return null;
    const p = data.pipeline;
    const t = p.total_products || 0;
    if (t <= 0) {
      if (!sfPending && storefront > 0) return 40;
      return null;
    }
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

  const healthBandKey =
    factoryHealthScore == null
      ? 'dashboard.health.loading'
      : factoryHealthScore >= 75
        ? 'dashboard.health.strong'
        : factoryHealthScore >= 50
          ? 'dashboard.health.fair'
          : 'dashboard.health.attention';

  const pipelineStatValue = (n: number) => (pipelineReady ? n : null);

  const stats = [
    {
      label: t(locale, 'dashboard.stat.total'),
      value: pipelineStatValue(total),
      icon: FileText,
      color: 'from-indigo-500 to-purple-500',
    },
    {
      label: t(locale, 'dashboard.stat.active'),
      value: pipelineStatValue(active),
      icon: Activity,
      color: 'from-emerald-500 to-teal-500',
    },
    {
      label: t(locale, 'dashboard.stat.shipped'),
      value: pipelineStatValue(completed),
      icon: CheckCircle2,
      color: 'from-green-500 to-emerald-500',
    },
    {
      label: t(locale, 'dashboard.stat.storefront'),
      value: sfPending ? null : storefront,
      icon: Store,
      color: 'from-cyan-500 to-sky-500',
    },
    {
      label: t(locale, 'dashboard.stat.rework'),
      value: pipelineStatValue(failed),
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
          {hadCacheOnMount
            ? t(locale, 'dashboard.refreshingCached')
            : t(locale, 'dashboard.loadingLive')}
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
                {failed === 1
                  ? tVars(locale, 'dashboard.failed.title', { n: failed })
                  : tVars(locale, 'dashboard.failed.titlePlural', { n: failed })}
              </h2>
              <p className="text-sm text-red-100/90 mt-1 max-w-3xl">{t(locale, 'dashboard.failed.body')}</p>
            </div>
          </motion.div>
          <ul className="space-y-3">
            {(failedAlerts.length > 0
              ? failedAlerts
              : [
                  {
                    product_id: '—',
                    title: t(locale, 'dashboard.failed.placeholderTitle'),
                    cause_plain: t(locale, 'dashboard.failed.placeholderCause'),
                  },
                ]
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
                  {item.cause_plain ||
                    item.failure_reason ||
                    t(locale, 'dashboard.failed.noReason')}
                </p>
                {item.failed_agent ? (
                  <p className="text-[11px] text-red-200/60 mt-1">
                    {tVars(locale, 'dashboard.failed.agent', { name: item.failed_agent })}
                  </p>
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
                <motion.div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-visible rounded-xl bg-gradient-to-br ${stat.color}`}
                >
                  <stat.icon className="h-5 w-5 text-white" strokeWidth={2} />
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
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center overflow-visible text-violet-400"
                aria-hidden
              >
                <Gauge className="h-6 w-6" strokeWidth={2} />
              </span>
              {t(locale, 'dashboard.health.title')}
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-400">{t(locale, 'dashboard.health.subtitle')}</p>
          </div>
          <div className="text-right">
            {factoryHealthScore == null ? (
              <p className="flex items-center justify-end gap-2 text-gray-400 text-sm">
                <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
                …
              </p>
            ) : (
              <p className="text-4xl font-bold text-violet-200 tabular-nums">{factoryHealthScore}</p>
            )}
            <p className="text-xs capitalize text-gray-500">{t(locale, healthBandKey)}</p>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar
            value={factoryHealthScore ?? 0}
            label={t(locale, 'dashboard.health.label')}
            variant={
              factoryHealthScore == null
                ? 'primary'
                : factoryHealthScore >= 70
                  ? 'success'
                  : 'warning'
            }
          />
        </div>
      </GlassCard>

      <GlassCard className="border border-cyan-500/25 bg-cyan-500/[0.04]">
        <motion.div className="flex flex-wrap items-start justify-between gap-4 mb-3">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold leading-normal text-white">
              <span
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center overflow-visible text-cyan-400"
                aria-hidden
              >
                <Store className="h-6 w-6" strokeWidth={2} />
              </span>
              {t(locale, 'dashboard.storefront.title')}
            </h3>
            <p className="text-sm text-gray-400 mt-1 max-w-3xl">{t(locale, 'dashboard.storefront.subtitle')}</p>
          </div>
          {sfPending ? (
            <div className="text-right shrink-0 flex items-center justify-end gap-2 text-gray-400 text-sm">
              <Loader2 className="w-5 h-5 animate-spin shrink-0" aria-hidden />
              <span>{t(locale, 'dashboard.storefront.loading')}</span>
            </div>
          ) : storefrontYieldPct !== null ? (
            <div className="text-right shrink-0">
              <p className="text-3xl font-bold text-cyan-300 tabular-nums">{storefrontYieldPct}%</p>
              <p className="text-xs text-gray-500">{t(locale, 'dashboard.storefront.yield')}</p>
            </div>
          ) : null}
        </motion.div>
        {sfPending ? (
          <p className="text-sm text-gray-500 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
            {t(locale, 'dashboard.storefront.loadingTotals')}
          </p>
        ) : storefrontYieldPct !== null ? (
          <>
            <ProgressBar
              value={storefrontYieldPct}
              label={t(locale, 'dashboard.storefront.conversion')}
              variant="success"
            />
            <p className="text-xs text-gray-500 mt-2 tabular-nums">
              {tVars(locale, 'dashboard.storefront.listed', {
                listed: storefront,
                completed,
              })}
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-500">{t(locale, 'dashboard.storefront.noCompleted')}</p>
        )}
      </GlassCard>

      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Pipeline Metrics</h3>
          <div className="space-y-4">
            {pipelineReady ? (
              <ProgressBar value={Math.round(completionRate)} label="Completion Rate" variant="success" />
            ) : (
              <p className="text-sm text-gray-500 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
                {t(locale, 'dashboard.loadingLive')}
              </p>
            )}
            <div className="flex justify-between text-sm text-gray-400">
              <span>Pending Tasks</span>
              <span className="text-white font-medium tabular-nums">
                {pipelineReady ? data.pipeline.pending_tasks : '…'}
              </span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Running Tasks</span>
              <span className="text-white font-medium tabular-nums">
                {pipelineReady ? data.pipeline.running_tasks : '…'}
              </span>
            </div>
            <div className="flex justify-between text-sm text-gray-400">
              <span>Timed Out Tasks</span>
              <span className="text-white font-medium tabular-nums">
                {pipelineReady ? data.pipeline.timed_out_tasks : '…'}
              </span>
            </div>
          </div>
        </GlassCard>

        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">System Resources</h3>
          <div className="space-y-4">
            {pipelineReady ? (
              <>
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
              </>
            ) : (
              <p className="text-sm text-gray-500 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin shrink-0" aria-hidden />
                {t(locale, 'dashboard.loadingLive')}
              </p>
            )}
          </div>
        </GlassCard>
      </div>

      <CostOutcomeHeatmap data={data.cost_outcome_heatmap as any} locale={locale} />

      <GlassCard className="p-4">
        <p className="text-xs text-gray-500">{t(locale, 'wow.aimarketEmbed')}</p>
      </GlassCard>

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
            <h3 className="text-lg font-semibold text-white">{t(locale, 'dashboard.security.title')}</h3>
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
