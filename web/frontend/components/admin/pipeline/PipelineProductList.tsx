'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  FileText,
  ClipboardList,
  Clock,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../tabs/pipelineConstants';
import { ProductPulse, type ProductPulsePayload } from '../tabs/ProductPulse';
import { HumanReviewGatePanel } from '../tabs/HumanReviewGatePanel';
import { StorefrontFollowupPanel } from '../tabs/StorefrontFollowupPanel';
import { PipelineProductFailedPanel } from './PipelineProductFailedPanel';
import { PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { bucketPipelineProductForCategoryFilter } from '@/lib/pipelineCategoryBucket';
import { formatRelativeTime, getStateLabel, formatDate } from '@/lib/utils';
import { pipelineTaskApiStatusLabel } from './pipelineTabHelpers';
import {
  findTaskForStage,
  formatTaskDuration,
  pipelineAgentEmoji,
} from '@/lib/pipelineProductHelpers';

export type PipelineCatalogProduct = Record<string, any> & {
  id: string;
  state?: string;
  idea?: string;
  created_at?: number;
  production_mode?: boolean;
  spec?: { product_name?: string; description?: string };
  task_counts?: { total?: number; completed?: number; running?: number; failed?: number };
  tasks?: Record<string, unknown>[];
  pulse?: ProductPulsePayload;
  economics?: Record<string, any>;
};

export type PipelineProductListProps = {
  locale: AdminLocale;
  filteredProducts: PipelineCatalogProduct[];
  productRowIndex: Map<string, number>;
  loadingMore: boolean;
  catalogLiveRowCount: number;
  productsLoaded: number;
  totalProducts: number;
  catalogHydrationPercent: number;
  expandedProduct: string | null;
  setExpandedProduct: (id: string | null) => void;
  loadSpec: (productId: string) => void;
  loadDeveloperHandoff: (productId: string) => void;
  openTaskDetailModal: (
    productId: string,
    productName: string,
    agentType: string,
    task: Record<string, unknown> | null,
  ) => void;
  mergeProductPatch: (productId: string, patch: Record<string, unknown>) => void;
};

export function PipelineProductList({
  locale,
  filteredProducts,
  productRowIndex,
  loadingMore,
  catalogLiveRowCount,
  productsLoaded,
  totalProducts,
  catalogHydrationPercent,
  expandedProduct,
  setExpandedProduct,
  loadSpec,
  loadDeveloperHandoff,
  openTaskDetailModal,
  mergeProductPatch,
}: PipelineProductListProps) {
  return (
    <>
      {filteredProducts.map((product, i) => {
        const taskCounts = product.task_counts || {};
        const totalTasks = taskCounts.total || 0;
        const completedTasks = taskCounts.completed || 0;
        const progress = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
        const isExpanded = expandedProduct === product.id;
        const tasks = product.tasks || [];
        const productTitle = product.spec?.product_name || product.idea || product.id;
        const catId = bucketPipelineProductForCategoryFilter(product as Record<string, unknown>);
        const rowOrder = productRowIndex.get(String(product.id)) ?? 0;
        const isSnapshotTail =
          loadingMore && catalogLiveRowCount > 0 && rowOrder >= catalogLiveRowCount;

        return (
          <motion.div
            key={product.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: isSnapshotTail ? 0.92 : 1, y: 0 }}
            transition={{
              delay: filteredProducts.length > 40 ? 0 : Math.min(i, 10) * 0.018,
              opacity: { duration: 0.35 },
            }}
          >
            <GlassCard>
              <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 items-start gap-3">
                  <span className={`shrink-0 text-[10px] font-medium px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[catId] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                    {CATEGORY_LABELS[catId] || catId}
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-white font-medium">
                      {product.spec?.product_name || product.idea || product.id}
                    </h3>
                    <p className="text-xs text-gray-500 font-mono mt-0.5">{product.id}</p>
                    {(() => {
                      const raw = Number(product?.created_at) || 0;
                      const sec = raw > 1e12 ? raw / 1000 : raw;
                      if (!sec) return null;
                      return (
                        <p className="text-[11px] text-gray-500 mt-0.5">
                          {tVars(locale, 'pipeline.card.created', {
                            date: formatDate(sec),
                          })}
                        </p>
                      );
                    })()}
                    {(product.spec?.description || (product.idea && product.idea !== productTitle)) && (
                      <p className="text-sm text-gray-400 mt-1.5 leading-relaxed">
                        {product.spec?.description || product.idea}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
                  <Badge variant={product.production_mode ? 'warning' : 'info'}>
                    {product.production_mode
                      ? t(locale, 'pipeline.card.modeProduction')
                      : t(locale, 'pipeline.card.modePrototype')}
                  </Badge>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => loadSpec(String(product.id))}
                  >
                    <FileText className="w-3.5 h-3.5 mr-1" />
                    {t(locale, 'pipeline.card.spec')}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => loadDeveloperHandoff(String(product.id))}
                    title={t(locale, 'pipeline.card.devHandoffTooltip')}
                  >
                    <ClipboardList className="w-3.5 h-3.5 mr-1" />
                    {t(locale, 'pipeline.card.devHandoff')}
                  </Button>
                  {String(product.state || '').toUpperCase() === 'FAILED' ? (
                    <span title={t(locale, 'pipeline.card.failedBadgeTooltip')}>
                      <Badge variant="error">{getStateLabel(product.state || '')}</Badge>
                    </span>
                  ) : (
                    <Badge
                      variant={
                        product.state === 'COMPLETED' || product.state === 'completed'
                          ? 'success'
                          : String(product.state || '').toUpperCase() === 'HUMAN_REVIEW_PENDING'
                            ? 'warning'
                            : 'info'
                      }
                    >
                      {getStateLabel(product.state || '')}
                    </Badge>
                  )}
                </div>
              </div>

              {/* ── Per-Product Economics Badges ─────────────────── */}
              {product.economics && (
                <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px]">
                  {/* LLM Cost */}
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                      (product.economics.llm_cost_usd || 0) > 5
                        ? 'bg-red-500/15 text-red-300 border border-red-500/20'
                        : (product.economics.llm_cost_usd || 0) > 1
                          ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                          : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                    }`}
                    title={tVars(locale, 'pipeline.economics.llmTooltip', {
                      cost: `$${(product.economics.llm_cost_usd || 0).toFixed(4)}`,
                      calls: product.economics.llm_call_count || 0,
                      tokens: (product.economics.llm_total_tokens || 0).toLocaleString(),
                    })}
                  >
                    <span className="text-[10px]">💰</span>
                    ${(product.economics.llm_cost_usd || 0).toFixed(2)}
                  </span>

                  {/* Quality Score */}
                  {product.economics.quality_score != null && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                        product.economics.quality_score >= 4
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                          : product.economics.quality_score >= 3
                            ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                            : 'bg-red-500/15 text-red-300 border border-red-500/20'
                      }`}
                      title={t(locale, 'pipeline.economics.qualityTooltip')}
                    >
                      <span className="text-[10px]">📊</span>
                      {product.economics.quality_score}/5
                    </span>
                  )}

                  {/* ROI Band */}
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                      product.economics.roi_band === 'green'
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                        : product.economics.roi_band === 'amber'
                          ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                          : 'bg-red-500/15 text-red-300 border border-red-500/20'
                    }`}
                    title={
                      product.economics.roi_band === 'green'
                        ? t(locale, 'pipeline.economics.roiTooltip.green')
                        : product.economics.roi_band === 'amber'
                          ? t(locale, 'pipeline.economics.roiTooltip.amber')
                          : t(locale, 'pipeline.economics.roiTooltip.red')
                    }
                  >
                    {product.economics.roi_band === 'green' ? '🟢' : product.economics.roi_band === 'amber' ? '🟡' : '🔴'}
                    {t(locale, 'pipeline.economics.roiSuffix')}
                  </span>

                  {/* Agent breakdown tooltip */}
                  {product.economics.llm_agent_breakdown &&
                    Object.keys(product.economics.llm_agent_breakdown).length > 0 && (
                      <span
                        className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium bg-white/5 text-gray-400 border border-white/10 cursor-help"
                        title={Object.entries(product.economics.llm_agent_breakdown)
                          .map(([agent, s]: [string, any]) =>
                            tVars(locale, 'pipeline.economics.agentSlice', {
                              agent,
                              cost: `$${(s.cost_usd || 0).toFixed(4)}`,
                              calls: s.calls,
                              tokens: (s.tokens || 0).toLocaleString(),
                            }),
                          )
                          .join(' · ')}
                      >
                        <span className="text-[10px]">🔍</span>
                        {tVars(locale, 'pipeline.economics.agentsCount', {
                          n: Object.keys(product.economics.llm_agent_breakdown).length,
                        })}
                      </span>
                    )}
                </div>
              )}

              {product.pulse && (
                <ProductPulse pulse={product.pulse as ProductPulsePayload} />
              )}

              {String(product.state || '').toUpperCase() === 'FAILED' && (
                <PipelineProductFailedPanel
                  productId={product.id}
                  productTitle={productTitle}
                  product={product as Record<string, unknown>}
                  onReopened={(patch) => mergeProductPatch(product.id, patch)}
                />
              )}

              {String(product.state || '').toUpperCase() === 'HUMAN_REVIEW_PENDING' && (
                <HumanReviewGatePanel product={product} onPatch={mergeProductPatch} />
              )}

              {(String(product.state || '').toUpperCase() === 'COMPLETED' ||
                String(product.state || '').toUpperCase() === 'DEPLOYED_PRODUCTION') && (
                <StorefrontFollowupPanel product={product} onPatch={mergeProductPatch} />
              )}

              {/* Pipeline Stage Flow Bar — always show full stage row (incl. Designer) even before tasks land in queue */}
              <div className="mb-4 overflow-x-auto">
                <p className="text-[10px] text-gray-500 mb-2">{t(locale, 'pipeline.stageFlow.hint')}</p>
                <div className="flex items-center min-w-max gap-0">
                  {(PIPELINE_STAGE_ORDER as readonly string[]).map((agentType, ai, arr) => {
                      const task = findTaskForStage(tasks, agentType);
                      const status = String(task?.status ?? 'pending');
                      /** Designer (UX) mirrors Architect — use fuchsia, not emerald, so it is not mistaken for a generic “green done” pipeline cell. */
                      const stageColors: Record<string, string> =
                        agentType === 'designer'
                          ? {
                              completed:
                                'bg-fuchsia-600 border-fuchsia-400 text-white',
                              running:
                                'bg-fuchsia-500 border-fuchsia-300 text-white animate-pulse',
                              failed: 'bg-red-500 border-red-400 text-red-900',
                              pending: 'bg-white/5 border-white/10 text-gray-500',
                            }
                          : {
                              completed:
                                'bg-emerald-500 border-emerald-400 text-emerald-900',
                              running:
                                'bg-amber-500 border-amber-400 text-amber-900 animate-pulse',
                              failed: 'bg-red-500 border-red-400 text-red-900',
                              pending: 'bg-white/5 border-white/10 text-gray-500',
                            };
                      const stageIcons: Record<string, string> = {
                        analyst: '🔍', pm: '📋', methodologist: '🧭',
                        architect: '🏗️', designer: '🎨', developer: '💻', qa: '🧪',
                        security: '🛡️', devops: '🚀', marketing: '📢',
                        sales: '💰',
                      };
                      const productTitle =
                        product.spec?.product_name || product.idea || product.id;
                      return (
                        <React.Fragment key={agentType}>
                          <div className="flex flex-col items-center gap-1 shrink-0 min-w-[2.5rem]">
                            <button
                              type="button"
                              title={
                                agentType === 'designer'
                                  ? t(locale, 'pipeline.stage.tileTitle.designer')
                                  : agentType === 'methodologist'
                                    ? t(locale, 'pipeline.stage.tileTitle.methodologist')
                                    : t(locale, 'pipeline.stage.tileTitle.default')
                              }
                              onClick={() =>
                                openTaskDetailModal(product.id, productTitle, agentType, task ? { ...task } : null)
                              }
                              className="flex flex-col items-center gap-1 rounded-xl p-0.5 -m-0.5 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-colors cursor-pointer group"
                            >
                              <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs border-2 transition-all group-hover:scale-105 ${stageColors[status] || 'bg-white/5 border-white/10 text-gray-500'}`}>
                                {stageIcons[agentType] || '⚙️'}
                              </div>
                              <span className={`text-[10px] font-medium ${
                                status === 'completed'
                                  ? agentType === 'designer'
                                    ? 'text-fuchsia-400'
                                    : 'text-emerald-400'
                                  : status === 'running'
                                    ? agentType === 'designer'
                                      ? 'text-fuchsia-300'
                                      : 'text-amber-400'
                                    : status === 'failed'
                                      ? 'text-red-400'
                                      : 'text-gray-600'
                              }`}>
                                {agentType === 'analyst'
                                  ? t(locale, 'pipeline.stage.abbr.analyst')
                                  : agentType === 'marketing'
                                    ? t(locale, 'pipeline.stage.abbr.marketing')
                                    : agentType === 'designer'
                                      ? t(locale, 'pipeline.stage.abbr.designer')
                                      : agentType === 'methodologist'
                                        ? t(locale, 'pipeline.stage.abbr.methodologist')
                                        : agentType === 'devops'
                                          ? t(locale, 'pipeline.stage.abbr.devops')
                                          : agentType.charAt(0).toUpperCase() + agentType.slice(1, 3)}
                              </span>
                            </button>
                          </div>
                          {ai < arr.length - 1 && (
                            <div className={`h-0.5 w-6 mx-1 rounded-full mt-[-18px] ${
                              status === 'completed'
                                ? agentType === 'designer'
                                  ? 'bg-fuchsia-500/50'
                                  : 'bg-emerald-500/50'
                                : status === 'running'
                                  ? agentType === 'designer'
                                    ? 'bg-fuchsia-500/30'
                                    : 'bg-amber-500/30'
                                  : 'bg-white/5'
                            }`} />
                          )}
                        </React.Fragment>
                      );
                    })}
                </div>
              </div>

              {/* Progress bar */}
              {totalTasks > 0 && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>{t(locale, 'pipeline.progress.label')}</span>
                    <span>
                      {tVars(locale, 'pipeline.progress.tasksPct', {
                        done: completedTasks,
                        total: totalTasks,
                        pct: progress,
                      })}
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between text-xs text-gray-500">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatRelativeTime(Number(product.created_at) || 0)}
                  </span>
                  <span>
                    {tVars(locale, 'pipeline.tasks.summary', {
                      total: totalTasks,
                      done: completedTasks,
                    })}
                  </span>
                  {(taskCounts.running ?? 0) > 0 && (
                    <span className="text-amber-400">
                      {tVars(locale, 'pipeline.tasks.running', { n: taskCounts.running ?? 0 })}
                    </span>
                  )}
                  {(taskCounts.failed ?? 0) > 0 && (
                    <span className="text-amber-400">
                      {tVars(locale, 'pipeline.tasks.rework', { n: taskCounts.failed ?? 0 })}
                    </span>
                  )}
                </div>
                {tasks.length > 0 && (
                  <button
                    onClick={() => setExpandedProduct(isExpanded ? null : product.id)}
                    className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    {isExpanded ? t(locale, 'pipeline.tasks.hide') : t(locale, 'pipeline.tasks.show')}
                    <ChevronRight className={`w-3.5 h-3.5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                  </button>
                )}
              </div>

              {/* Expandable Task Timeline */}
              {isExpanded && tasks.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-4 border-t border-white/5 pt-4"
                >
                  <div className="space-y-0">
                    {tasks.map((task: any, ti: number) => {
                      const taskStatus = task.status || 'pending';
                      const statusColors: Record<string, string> = {
                        completed: 'border-emerald-500 bg-emerald-500/20',
                        running: 'border-amber-500 bg-amber-500/20',
                        failed: 'border-red-500 bg-red-500/20',
                        pending: 'border-gray-600 bg-gray-600/20',
                      };
                      const dotColors: Record<string, string> = {
                        completed: 'bg-emerald-500 shadow-emerald-500/50',
                        running: 'bg-amber-500 animate-pulse shadow-amber-500/50',
                        failed: 'bg-red-500 shadow-red-500/50',
                        pending: 'bg-gray-600',
                      };

                      return (
                        <div key={task.id || ti} className="flex gap-3 relative pb-4 last:pb-0">
                          {/* Timeline connector line */}
                          {ti < tasks.length - 1 && (
                            <div className="absolute left-[15px] top-[30px] bottom-0 w-px bg-white/5" />
                          )}

                          {/* Status dot — click opens same detail modal as the stage bar */}
                          <div className="flex-shrink-0 mt-1.5">
                            <button
                              type="button"
                              title={t(locale, 'pipeline.task.openDetailsTitle')}
                              onClick={() =>
                                openTaskDetailModal(
                                  product.id,
                                  product.spec?.product_name || product.idea || product.id,
                                  String(task.agent_type || ''),
                                  task as Record<string, unknown>
                                )
                              }
                              className={`w-[30px] h-[30px] rounded-full flex items-center justify-center border transition-transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 ${statusColors[taskStatus] || 'border-gray-600 bg-gray-600/20'}`}
                            >
                              <span className="text-xs">{pipelineAgentEmoji(task.agent_type)}</span>
                            </button>
                          </div>

                          {/* Task details */}
                          <div className="flex-1 min-w-0 pt-0.5">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-sm font-medium text-white capitalize">
                                {task.agent_type?.replace(/_/g, ' ') || t(locale, 'pipeline.task.unknownAgent')}
                              </span>
                              <div className="flex items-center gap-2">
                                <span className={`text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded ${
                                  taskStatus === 'completed' ? 'text-emerald-400 bg-emerald-500/10' :
                                  taskStatus === 'running' ? 'text-amber-400 bg-amber-500/10' :
                                  taskStatus === 'failed' ? 'text-red-400 bg-red-500/10' :
                                  'text-gray-500 bg-gray-500/10'
                                }`}>
                                  {pipelineTaskApiStatusLabel(locale, String(taskStatus))}
                                </span>
                              </div>
                            </div>

                            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500">
                              {task.started_at && (
                                <span>
                                  {tVars(locale, 'pipeline.task.meta.started', {
                                    time: new Date(task.started_at * 1000).toLocaleTimeString(),
                                  })}
                                </span>
                              )}
                              {task.completed_at && (
                                <span>
                                  {tVars(locale, 'pipeline.task.meta.completed', {
                                    time: new Date(task.completed_at * 1000).toLocaleTimeString(),
                                  })}
                                </span>
                              )}
                              {task.started_at && task.completed_at && (
                                <span>
                                  {tVars(locale, 'pipeline.task.meta.duration', {
                                    dur: formatTaskDuration(task.started_at, task.completed_at),
                                  })}
                                </span>
                              )}
                              {task.metrics?.llm_time_ms && (
                                <span>
                                  {tVars(locale, 'pipeline.task.meta.llm', {
                                    sec: (task.metrics.llm_time_ms / 1000).toFixed(1),
                                  })}
                                </span>
                              )}
                            </div>

                            {/* Error message for failed tasks */}
                            {task.error && (
                              <div className="mt-1 text-[11px] text-red-400 bg-red-500/5 rounded px-2 py-1 border border-red-500/10">
                                {task.error}
                              </div>
                            )}

                            {/* State info */}
                            {task.state && (
                              <div className="mt-0.5 text-[10px] text-gray-600 font-mono">
                                {tVars(locale, 'pipeline.task.stateLabel', { state: task.state })}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </GlassCard>
          </motion.div>
        );
      })}
      {loadingMore && filteredProducts.length > 0 && (
        <div className="py-4 flex flex-col items-center justify-center px-2 gap-2">
          <p className="text-[11px] text-slate-500 text-center max-w-md flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
            <RefreshCw className="w-3 h-3 shrink-0 animate-spin text-slate-500" aria-hidden />
            <span>
              {tVars(locale, 'pipeline.syncingCatalog', {
                loaded: productsLoaded,
                total: totalProducts,
                pct: catalogHydrationPercent,
              })}
            </span>
          </p>
          <div
            className="w-full max-w-md h-1.5 overflow-hidden rounded-full bg-white/10"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={catalogHydrationPercent}
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500/90 to-teal-500/80 transition-[width] duration-300 ease-out"
              style={{ width: `${catalogHydrationPercent}%` }}
            />
          </div>
        </div>
      )}
      {!loadingMore && productsLoaded > 0 && productsLoaded >= totalProducts && (
        <p className="text-center text-xs text-gray-600 py-2">
          {tVars(locale, 'pipeline.endOfList', { total: totalProducts || productsLoaded })}
        </p>
      )}

    </>
  );
}
