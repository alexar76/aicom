'use client';

import React from 'react';
import { FileText, ClipboardList } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Badge } from '@/components/ui/Badge';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { STAGE_AGENT_TITLE } from '../tabs/pipelineConstants';
import { formatTaskDuration, formatTaskWhen, safeJson, toUnixSeconds } from '@/lib/pipelineProductHelpers';
import { pipelineTaskApiStatusLabel } from './pipelineTabHelpers';

export type PipelineTabModalsProps = {
  locale: AdminLocale;
  specModalProduct: string | null;
  closeSpecModal: () => void;
  specLoading: boolean;
  specData: any;
  handoffModalProduct: string | null;
  closeHandoffModal: () => void;
  handoffLoading: boolean;
  handoffData: any;
  taskStageModal: {
    productId: string;
    productName: string;
    agentType: string;
    task: Record<string, unknown> | null;
  } | null;
  setTaskStageModal: (v: PipelineTabModalsProps['taskStageModal']) => void;
};

export function PipelineTabModals(props: PipelineTabModalsProps) {
  const {
    locale,
    specModalProduct,
    closeSpecModal,
    specLoading,
    specData,
    handoffModalProduct,
    closeHandoffModal,
    handoffLoading,
    handoffData,
    taskStageModal,
    setTaskStageModal,
  } = props;

  return (
    <>
      {/* Spec Viewer Modal */}
      <Modal
        isOpen={specModalProduct !== null}
        onClose={closeSpecModal}
        title={t(locale, 'pipeline.modals.specTitle')}
        size="xl"
      >
        {specLoading ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-gray-500">{t(locale, 'pipeline.modals.loadingSpec')}</p>
          </div>
        ) : specData ? (
          <div className="space-y-6 max-h-[70vh] overflow-y-auto">
            {specData.product_name && (
              <div>
                <h3 className="text-sm text-gray-500 mb-1">{t(locale, 'pipeline.modals.spec.productName')}</h3>
                <p className="text-white font-medium text-lg">{specData.product_name}</p>
              </div>
            )}
            {specData.description && (
              <div>
                <h3 className="text-sm text-gray-500 mb-1">{t(locale, 'pipeline.modals.spec.description')}</h3>
                <p className="text-gray-300 text-sm whitespace-pre-wrap">{specData.description}</p>
              </div>
            )}
            {specData.core_features && specData.core_features.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">{t(locale, 'pipeline.modals.spec.coreFeatures')}</h3>
                <ul className="space-y-1.5">
                  {specData.core_features.map((feature: string, fi: number) => (
                    <li key={fi} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-indigo-400 mt-0.5">•</span>
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {specData.user_stories && specData.user_stories.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">{t(locale, 'pipeline.modals.spec.userStories')}</h3>
                <ul className="space-y-1.5">
                  {specData.user_stories.map((story: string, si: number) => (
                    <li key={si} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-emerald-400 mt-0.5">•</span>
                      {story}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {specData.technical_risks && specData.technical_risks.length > 0 && (
              <div>
                <h3 className="text-sm text-gray-500 mb-2">{t(locale, 'pipeline.modals.spec.technicalRisks')}</h3>
                <ul className="space-y-1.5">
                  {specData.technical_risks.map((risk: string, ri: number) => (
                    <li key={ri} className="flex items-start gap-2 text-sm text-amber-300">
                      <span className="text-amber-400 mt-0.5">⚠</span>
                      {risk}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!specData.product_name && !specData.description && !specData.core_features && (
              <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono bg-black/30 p-4 rounded-lg max-h-[50vh] overflow-y-auto">
                {JSON.stringify(specData, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">{t(locale, 'pipeline.modals.noSpec')}</p>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={handoffModalProduct !== null}
        onClose={closeHandoffModal}
        title={t(locale, 'pipeline.modals.handoffTitle')}
        size="xl"
      >
        {handoffLoading ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-gray-500">{t(locale, 'pipeline.modals.loadingDev')}</p>
          </div>
        ) : handoffData ? (
          <div className="space-y-4 max-h-[72vh] overflow-y-auto pr-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-gray-500">{t(locale, 'pipeline.modals.handoff.product')}</span>
              <code className="text-[11px] text-cyan-300 bg-black/30 px-2 py-0.5 rounded">{handoffData.product_id}</code>
              <Badge
                variant={
                  handoffData.material_summary.quality_band === 'weak'
                    ? 'error'
                    : handoffData.material_summary.quality_band === 'thin'
                      ? 'warning'
                      : 'success'
                }
              >
                {tVars(locale, 'pipeline.modals.handoff.material', {
                  band: handoffData.material_summary.quality_band,
                })}
              </Badge>
              <span className="text-xs text-gray-500">
                delivery_mode={handoffData.delivery_mode}
                {handoffData.delivery_profile ? ` · profile=${handoffData.delivery_profile}` : ''}
              </span>
            </div>
            {handoffData.material_summary.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 space-y-1.5">
                <p className="text-xs font-medium text-amber-200">{t(locale, 'pipeline.modals.handoff.warnings')}</p>
                <ul className="list-disc list-inside text-xs text-amber-100/90 space-y-1">
                  {handoffData.material_summary.warnings.map((w: string, wi: number) => (
                    <li key={wi}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-2 text-[11px] text-gray-400">
              {Object.entries(handoffData.material_summary.stats || {}).map(([k, v]) => (
                <span key={k} className="rounded-md bg-white/5 border border-white/10 px-2 py-0.5 font-mono">
                  {k}: {String(v)}
                </span>
              ))}
            </div>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">
                {t(locale, 'pipeline.modals.handoff.adminInstructions')}
              </summary>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans px-3 pb-3 max-h-48 overflow-y-auto">
                {handoffData.admin_instructions?.trim() || t(locale, 'pipeline.modals.handoff.adminEmpty')}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">
                {t(locale, 'pipeline.modals.handoff.analystBrief')}
              </summary>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans px-3 pb-3 max-h-56 overflow-y-auto">
                {handoffData.analyst_brief_for_developer?.trim() ||
                  t(locale, 'pipeline.modals.handoff.analystBriefEmpty')}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">
                {t(locale, 'pipeline.modals.handoff.specJson')}
              </summary>
              <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {safeJson(handoffData.specification)}
              </pre>
            </details>
            <details className="rounded-lg border border-white/10 bg-black/20 open:bg-black/30">
              <summary className="cursor-pointer text-sm text-indigo-300 px-3 py-2">
                {t(locale, 'pipeline.modals.handoff.archJson')}
              </summary>
              <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {safeJson(handoffData.architecture)}
              </pre>
            </details>
          </div>
        ) : (
          <div className="text-center py-12">
            <ClipboardList className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">{t(locale, 'pipeline.modals.handoff.error')}</p>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={taskStageModal !== null}
        onClose={() => setTaskStageModal(null)}
        title={
          taskStageModal
            ? tVars(locale, 'pipeline.modals.task.title', {
                agent: STAGE_AGENT_TITLE[taskStageModal.agentType] || taskStageModal.agentType,
              })
            : ''
        }
        size="xl"
        className="max-w-2xl max-h-[90vh] flex flex-col"
      >
        {taskStageModal && (
          <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1 text-sm">
            <div className="rounded-xl bg-white/5 border border-white/10 p-3">
              <p className="text-xs text-gray-500 mb-0.5">{t(locale, 'pipeline.modals.task.productLabel')}</p>
              <p className="text-white font-medium">{taskStageModal.productName}</p>
              <p className="text-[11px] text-gray-500 font-mono mt-1">{taskStageModal.productId}</p>
            </div>

            {taskStageModal.agentType === 'designer' && taskStageModal.task && (
              <p className="text-xs text-fuchsia-200/95 bg-fuchsia-500/10 border border-fuchsia-500/25 rounded-lg px-3 py-2 leading-relaxed">
                {t(locale, 'pipeline.modals.task.designerNote')}
              </p>
            )}

            {!taskStageModal.task && (
              <p className="text-gray-400 text-sm leading-relaxed">{t(locale, 'pipeline.modals.task.noTask')}</p>
            )}

            {taskStageModal.task && (() => {
              const taskRec = taskStageModal.task;
              const st = (taskRec.status as string) || 'unknown';
              const sc = toUnixSeconds(taskRec.started_at);
              const ec = toUnixSeconds(taskRec.completed_at);
              const cc = toUnixSeconds(taskRec.created_at);
              const durMain =
                sc !== undefined && ec !== undefined ? formatTaskDuration(sc, ec) : '';
              const durQueue =
                cc !== undefined && sc !== undefined ? formatTaskDuration(cc, sc) : '';
              const out = taskRec.output_data as Record<string, unknown> | undefined;
              const inp = taskRec.input_data as Record<string, unknown> | undefined;
              const criticFeedback =
                (inp && typeof inp.critic_feedback === 'object' && inp.critic_feedback !== null
                  ? (inp.critic_feedback as Record<string, unknown>)
                  : undefined) ||
                (out && typeof out.critic_feedback === 'object' && out.critic_feedback !== null
                  ? (out.critic_feedback as Record<string, unknown>)
                  : undefined);
              const metrics =
                (taskRec.metrics as Record<string, unknown> | undefined) ||
                (out && typeof out.metrics === 'object' && out.metrics !== null
                  ? (out.metrics as Record<string, unknown>)
                  : undefined);

              return (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-gray-500">{t(locale, 'pipeline.modals.task.taskId')}</span>
                    <code className="text-[11px] text-cyan-300 bg-black/30 px-2 py-0.5 rounded">
                      {String(taskRec.id ?? '—')}
                    </code>
                    <span
                      className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded font-medium ${
                        st === 'completed'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : st === 'running'
                            ? 'bg-amber-500/15 text-amber-300'
                            : st === 'failed'
                              ? 'bg-red-500/15 text-red-400'
                              : 'bg-white/10 text-gray-400'
                      }`}
                    >
                      {pipelineTaskApiStatusLabel(locale, st)}
                    </span>
                  </div>

                  {taskRec.state != null && (
                    <p className="text-xs text-gray-500">
                      {t(locale, 'pipeline.modals.task.targetState')}{' '}
                      <span className="text-gray-300 font-mono">{String(taskRec.state)}</span>
                    </p>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">{t(locale, 'pipeline.modals.task.created')}</p>
                      <p className="text-gray-200">{formatTaskWhen(taskRec.created_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">{t(locale, 'pipeline.modals.task.started')}</p>
                      <p className="text-gray-200">{formatTaskWhen(taskRec.started_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">{t(locale, 'pipeline.modals.task.completed')}</p>
                      <p className="text-gray-200">{formatTaskWhen(taskRec.completed_at)}</p>
                    </div>
                    <div className="rounded-lg bg-black/20 border border-white/10 p-2.5">
                      <p className="text-gray-500 mb-1">{t(locale, 'pipeline.modals.task.durations')}</p>
                      <p className="text-gray-200">
                        {durMain ? (
                          <span>{tVars(locale, 'pipeline.modals.task.work', { dur: durMain })}</span>
                        ) : (
                          <span className="text-gray-500">{t(locale, 'pipeline.modals.task.workEmpty')}</span>
                        )}
                        {durQueue ? (
                          <span className="block mt-0.5">
                            {tVars(locale, 'pipeline.modals.task.inQueue', { dur: durQueue })}
                          </span>
                        ) : null}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-400">
                    {taskRec.timeout_sec != null && (
                      <span>
                        {tVars(locale, 'pipeline.modals.task.timeout', { sec: String(taskRec.timeout_sec) })}
                      </span>
                    )}
                    {taskRec.priority != null && (
                      <span>
                        {tVars(locale, 'pipeline.modals.task.priority', { p: String(taskRec.priority) })}
                      </span>
                    )}
                    {(taskRec.retry_count != null || taskRec.max_retries != null) && (
                      <span>
                        {tVars(locale, 'pipeline.modals.task.retries', {
                          cur: String(taskRec.retry_count ?? 0),
                          max: String(taskRec.max_retries ?? '—'),
                        })}
                      </span>
                    )}
                  </div>

                  {metrics && Object.keys(metrics).length > 0 && (
                    <details open className="rounded-lg border border-indigo-500/20 bg-indigo-500/5">
                      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-indigo-200">
                        {t(locale, 'pipeline.modals.task.metrics')}
                      </summary>
                      <pre className="text-[11px] text-gray-400 font-mono px-3 pb-3 overflow-x-auto">
                        {safeJson(metrics, 32_000)}
                      </pre>
                    </details>
                  )}

                  {criticFeedback && (
                    <details open className="rounded-lg border border-amber-500/30 bg-amber-500/10">
                      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-amber-200">
                        {t(locale, 'pipeline.modals.task.critic')}
                      </summary>
                      <pre className="text-[11px] text-amber-100/90 font-mono px-3 pb-3 overflow-x-auto whitespace-pre-wrap">
                        {safeJson(criticFeedback, 24_000)}
                      </pre>
                    </details>
                  )}

                  {taskRec.error != null && String(taskRec.error).trim() !== '' && (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300 whitespace-pre-wrap">
                      {String(taskRec.error)}
                    </div>
                  )}

                  {inp && Object.keys(inp).length > 0 && (
                    <details className="rounded-lg border border-white/10 bg-black/20">
                      <summary className="cursor-pointer px-3 py-2 text-xs text-gray-400">
                        {t(locale, 'pipeline.modals.task.inputData')}
                      </summary>
                      <pre className="text-[11px] text-gray-500 font-mono px-3 pb-3 max-h-48 overflow-auto">
                        {safeJson(inp)}
                      </pre>
                    </details>
                  )}

                  {out && Object.keys(out).length > 0 && (
                    <details className="rounded-lg border border-white/10 bg-black/20">
                      <summary className="cursor-pointer px-3 py-2 text-xs text-gray-400">
                        {t(locale, 'pipeline.modals.task.outputData')}
                      </summary>
                      <pre className="text-[11px] text-gray-500 font-mono px-3 pb-3 max-h-64 overflow-auto">
                        {safeJson(out)}
                      </pre>
                    </details>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </Modal>

    </>
  );
}
