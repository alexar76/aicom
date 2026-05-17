'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ExternalLink, Loader2, RefreshCw, ScrollText, Terminal } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { GlassCard } from '@/components/ui/GlassCard';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import api, { AgentStatus } from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS } from '@/lib/pipelineStages';
import { formatDate, formatRelativeTime, getAgentIcon } from '@/lib/utils';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

function agentTitle(locale: AdminLocale, agent: AgentStatus): string {
  if (agent.type === 'designer') return t(locale, 'agents.role.designerUx');
  if (agent.type === 'methodologist') return t(locale, 'agents.role.methodologist');
  return agent.type.replace(/_/g, ' ');
}

function formatLogLineTime(ts: number): string {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function AgentsTab({ locale }: { locale: AdminLocale }) {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentStatus[]>(() => INITIAL_AGENTS_TAB_ROWS as AgentStatus[]);
  const [detail, setDetail] = useState<AgentStatus | null>(null);
  const [detailLogs, setDetailLogs] = useState<any[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const loadAgents = useCallback(() => {
    api.getAgents().then(setAgents).catch(() => {});
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    if (!detail) {
      setDetailLogs([]);
      return;
    }
    let cancelled = false;
    setLogsLoading(true);
    api
      .getAgentLogs(detail.type, 60)
      .then((data) => {
        if (cancelled) return;
        const rows = data.logs || [];
        setDetailLogs([...rows].reverse());
      })
      .catch(() => {
        if (!cancelled) setDetailLogs([]);
      })
      .finally(() => {
        if (!cancelled) setLogsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [detail]);

  const openLlmLogs = (type: string) => {
    router.push(`/admin?tab=llm-logs&llmAgent=${encodeURIComponent(type)}`);
  };

  const openAgentLogs = (type: string) => {
    router.push(`/admin?tab=agent-logs&agentLog=${encodeURIComponent(type)}`);
  };

  const openPipeline = (type: string) => {
    router.push(`/admin?tab=pipeline&pipelineSearch=${encodeURIComponent(type)}`);
  };

  const refreshAgentsAndDetail = useCallback(async () => {
    const list = await api.getAgents();
    setAgents(list);
    setDetail((d) => {
      if (!d) return null;
      return list.find((a) => a.type === d.type) ?? d;
    });
  }, []);

  const lastActiveSec = (a: AgentStatus): number => {
    const tail = typeof a.last_active === 'number' ? a.last_active : 0;
    const m = a.log_metrics?.last_active;
    const metric = typeof m === 'number' && m > 0 ? m : 0;
    return Math.max(tail > 1e12 ? tail / 1000 : tail, metric > 1e12 ? metric / 1000 : metric);
  };

  return (
    <motion.div className="space-y-4">
      <h2 className="text-xl font-semibold text-white mb-4">{t(locale, 'agents.title')}</h2>
      <p className="text-xs text-gray-500 mb-4 max-w-2xl">
        <strong className="text-gray-400">{t(locale, 'agents.intro.boldDesigner')}</strong>
        {t(locale, 'agents.intro.beforeCode')}
        <code className="text-cyan-400/90">ui_experience</code>
        {t(locale, 'agents.intro.afterCode')}
        <strong className="text-gray-400">{t(locale, 'agents.intro.boldDesignCritic')}</strong>
        {t(locale, 'agents.intro.and')}
        <strong className="text-gray-400">{t(locale, 'agents.intro.boldHardening')}</strong>
        {t(locale, 'agents.intro.afterStages')}
        <strong className="text-gray-400">{t(locale, 'agents.intro.boldLumen')}</strong>
        {t(locale, 'agents.intro.afterLumen')}
        <span className="block mt-2 text-gray-500">{t(locale, 'agents.intro.clickHint')}</span>
      </p>
      <motion.div className="grid md:grid-cols-2 gap-4">
        {agents.map((agent, i) => (
          <motion.div
            key={agent.type}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <button
              type="button"
              onClick={() => setDetail(agent)}
              className="w-full text-left rounded-2xl transition-colors hover:ring-1 hover:ring-indigo-500/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50"
            >
              <GlassCard className="h-full cursor-pointer">
                <div className="flex items-center gap-4">
                  <div className="text-3xl shrink-0">{getAgentIcon(agent.type)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <h3 className="text-white font-medium capitalize">{agentTitle(locale, agent)}</h3>
                      <Badge
                        variant={
                          agent.status === 'running'
                            ? 'success'
                            : agent.status === 'error' || agent.status === 'offline'
                              ? 'error'
                              : 'info'
                        }
                      >
                        {agent.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      {tVars(locale, 'agents.card.tasksCompleted', { count: agent.tasks_completed })}
                    </p>
                  </div>
                </div>
              </GlassCard>
            </button>
          </motion.div>
        ))}
      </motion.div>

      <Modal
        isOpen={detail != null}
        onClose={() => setDetail(null)}
        title={detail ? agentTitle(locale, detail) : ''}
        size="2xl"
        className="max-h-[min(92dvh,calc(100vh-1rem))]"
      >
        {detail && (
          <div className="space-y-5 pt-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={
                  detail.status === 'running'
                    ? 'success'
                    : detail.status === 'error' || detail.status === 'offline'
                      ? 'error'
                      : 'info'
                }
              >
                {detail.status}
              </Badge>
              <span className="text-xs text-gray-500 font-mono">{detail.type}</span>
            </div>

            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-gray-500">
                  {t(locale, 'agents.modal.tasksCompleted')}
                </dt>
                <dd className="text-white font-medium tabular-nums">{detail.tasks_completed}</dd>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-gray-500">
                  {t(locale, 'agents.modal.timeout')}
                </dt>
                <dd className="text-white font-medium tabular-nums">
                  {typeof detail.timeout === 'number' && detail.timeout > 0 ? detail.timeout : '—'}
                </dd>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 sm:col-span-2">
                <dt className="text-[10px] uppercase tracking-wide text-gray-500">
                  {t(locale, 'agents.modal.lastActivity')}
                </dt>
                <dd className="text-gray-200">
                  {lastActiveSec(detail) > 0 ? (
                    <>
                      <span className="text-white">{formatDate(lastActiveSec(detail))}</span>
                      <span className="text-gray-500"> · {formatRelativeTime(lastActiveSec(detail))}</span>
                    </>
                  ) : (
                    <span className="text-gray-500">{t(locale, 'agents.modal.noTimestampsYet')}</span>
                  )}
                </dd>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 sm:col-span-2">
                <dt className="text-[10px] uppercase tracking-wide text-gray-500">
                  {t(locale, 'agents.modal.currentTask')}
                </dt>
                <dd className="text-gray-200 break-words">
                  {detail.current_task ? detail.current_task : <span className="text-gray-500">—</span>}
                </dd>
              </div>
            </dl>

            {detail.log_metrics && (
              <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.06] px-3 py-3">
                <p className="text-xs font-medium text-cyan-200/90 mb-2">{t(locale, 'agents.modal.metricsTitle')}</p>
                <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  <div>
                    <dt className="text-gray-500">{t(locale, 'agents.modal.metricTotalLines')}</dt>
                    <dd className="text-white tabular-nums">{detail.log_metrics.total_entries}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">{t(locale, 'agents.modal.metricRecent1h')}</dt>
                    <dd className="text-white tabular-nums">{detail.log_metrics.recent_entries}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">{t(locale, 'agents.modal.metricErrors1h')}</dt>
                    <dd className="text-amber-300 tabular-nums">{detail.log_metrics.recent_errors}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">{t(locale, 'agents.modal.metricDerivedStatus')}</dt>
                    <dd className="text-gray-200">{detail.log_metrics.status}</dd>
                  </div>
                </dl>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => openLlmLogs(detail.type)}>
                <ScrollText className="w-4 h-4 mr-1.5" aria-hidden />
                {t(locale, 'agents.btn.llmLogs')}
              </Button>
              <Button type="button" variant="secondary" size="sm" onClick={() => openAgentLogs(detail.type)}>
                <Terminal className="w-4 h-4 mr-1.5" aria-hidden />
                {t(locale, 'agents.btn.agentLogs')}
              </Button>
              <Button type="button" variant="secondary" size="sm" onClick={() => openPipeline(detail.type)}>
                <ExternalLink className="w-4 h-4 mr-1.5" aria-hidden />
                {t(locale, 'agents.btn.pipeline')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void refreshAgentsAndDetail()}
                title={t(locale, 'agents.btn.refreshDataTitle')}
              >
                <RefreshCw className="w-4 h-4 mr-1.5" aria-hidden />
                {t(locale, 'agents.btn.refreshData')}
              </Button>
            </div>
            <p className="text-[10px] text-gray-500">{t(locale, 'agents.pipelineSearchHint')}</p>

            <div>
              <h4 className="text-sm font-medium text-white mb-2">{t(locale, 'agents.recentExecutionLog')}</h4>
              {logsLoading ? (
                <div className="flex items-center gap-2 py-8 text-gray-400 text-sm">
                  <Loader2 className="h-5 w-5 animate-spin text-indigo-400" aria-hidden />
                  {t(locale, 'agents.loadingDots')}
                </div>
              ) : detailLogs.length === 0 ? (
                <p className="text-sm text-gray-500 py-4">{t(locale, 'agents.noLogEntries')}</p>
              ) : (
                <ul className="max-h-56 space-y-2 overflow-y-auto rounded-lg border border-white/10 bg-black/20 p-2 text-xs">
                  {detailLogs.map((log, idx) => (
                    <li key={`${log.time}-${idx}`} className="border-b border-white/5 pb-2 last:border-0 last:pb-0">
                      <span className="text-gray-500 font-mono">{formatLogLineTime(Number(log.time) || 0)}</span>
                      <p className="text-gray-300 mt-0.5 break-words">{String(log.message || log.content || '—')}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>
    </motion.div>
  );
}
