'use client';

import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { getFailureSummary } from '@/lib/pipelineProductHelpers';
import type { PipelineFailureReport } from '@/lib/pipelineFailureReport';

type Props = {
  productId: string;
  productTitle: string;
  product: Record<string, unknown>;
  onReopened?: (patch: Record<string, unknown>) => void;
};

export function PipelineProductFailedPanel({
  productId,
  productTitle,
  product,
  onReopened,
}: Props) {
  const report = (product.failure_report as PipelineFailureReport | undefined) ?? null;
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTechnical, setShowTechnical] = useState(false);

  const fallbackLines = useMemo(() => getFailureSummary(product), [product]);
  const headline = report?.headline ?? 'Pipeline stopped';
  const cause =
    report?.cause_plain ??
    (fallbackLines.length ? fallbackLines.join(' ') : 'Failure reason is not stored.');
  const technical = report?.technical_errors?.length
    ? report.technical_errors
    : fallbackLines;
  const recovery = report?.suggested_recovery;

  const submit = async () => {
    const trimmed = notes.trim();
    if (trimmed.length < 8) {
      setError('Add at least 8 characters: what to fix and what “done” looks like.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.postPipelineReopenFailed(productId, trimmed, {
        agent_type: recovery?.agent_type,
        target_state: recovery?.target_state,
      });
      onReopened?.({
        state: res.product_state ?? 'MARKET_RESEARCHED',
        failure_reason: undefined,
        last_error: undefined,
        failure_report: undefined,
      });
      setNotes('');
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'message' in e
          ? String((e as { message?: string }).message)
          : 'Could not send to rework';
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 rounded-2xl border-2 border-red-500/50 bg-gradient-to-br from-red-950/80 via-red-900/30 to-amber-950/20 p-4 sm:p-5 shadow-lg shadow-red-900/20"
    >
      <motion.div className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <motion.div
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-red-500/25 border border-red-400/40"
          >
            <AlertTriangle className="h-6 w-6 text-red-300" aria-hidden />
          </motion.div>
          <motion.div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-red-300/90">
              Not finished — paused, not deleted
            </p>
            <h3 className="text-lg font-semibold text-red-50 mt-0.5">{headline}</h3>
            <p className="text-sm text-red-100/95 mt-2 leading-relaxed">{cause}</p>
            {(report?.failed_agent || report?.failed_stage) && !report?.false_failed && (
              <p className="text-xs text-red-200/70 mt-2">
                Stage: <span className="text-red-100">{report?.failed_stage ?? '—'}</span>
                {report?.failed_agent ? (
                  <>
                    {' · '}
                    Agent: <span className="text-red-100">{report.failed_agent}</span>
                  </>
                ) : null}
              </p>
            )}
            {typeof report?.pm_spec_requeue_count === 'number' && (
              <p className="text-xs text-amber-200/80 mt-1">
                Auto PM retries used: {report.pm_spec_requeue_count}
              </p>
            )}
          </motion.div>
        </div>

        {technical.length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowTechnical((v) => !v)}
              className="text-xs text-red-200 underline underline-offset-2 hover:text-red-50"
            >
              {showTechnical ? 'Hide' : 'Show'} technical log ({technical.length})
            </button>
            {showTechnical && (
              <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-red-500/20 bg-black/40 p-3 text-[11px] text-red-100/90 whitespace-pre-wrap">
                {technical.join('\n\n---\n\n')}
              </pre>
            )}
          </div>
        )}

        <motion.div className="flex flex-col gap-2">
          <label htmlFor={`reopen-notes-${productId}`} className="text-xs font-medium text-red-200">
            Instructions for the next agent run ({productTitle})
          </label>
          <textarea
            id={`reopen-notes-${productId}`}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Example: Expand acceptance criteria for onboarding; add NFR for API latency; fix methodology section 3…"
            className="w-full rounded-xl border border-red-500/30 bg-black/30 px-3 py-2 text-sm text-red-50 placeholder:text-red-300/40 focus:outline-none focus:ring-2 focus:ring-red-400/50"
          />
          {report?.operator_hint && (
            <p className="text-[11px] text-red-200/70">{report.operator_hint}</p>
          )}
          {recovery && (
            <p className="text-[11px] text-amber-200/80">
              Planned recovery: {recovery.agent_type} → {recovery.target_state}
            </p>
          )}
          {error && <p className="text-sm text-red-300">{error}</p>}
        </motion.div>

        <Button
          variant="primary"
          size="lg"
          disabled={busy}
          onClick={() => void submit()}
          className="w-full sm:w-auto min-h-[48px] text-base font-semibold bg-red-600 hover:bg-red-500 border-red-400/50 shadow-md"
        >
          {busy ? (
            <>
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Sending to rework…
            </>
          ) : (
            <>
              <RefreshCw className="w-5 h-5 mr-2" />
              Send to rework
            </>
          )}
        </Button>
      </motion.div>
    </motion.div>
  );
}
