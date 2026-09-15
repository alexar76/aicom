'use client';

import { useEffect, useState } from 'react';
import { Pause } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import { t, type AdminLocale } from '@/lib/adminI18n';

type Props = {
  locale: AdminLocale;
  productId: string;
  storefrontFollowup?: Record<string, unknown> | null;
  pipelineFocusActive?: boolean;
  onPatch: (productId: string, patch: Record<string, unknown>) => void;
  compact?: boolean;
};

export function ProductPipelineHoldToggle({
  locale,
  productId,
  storefrontFollowup,
  pipelineFocusActive = false,
  onPatch,
  compact = false,
}: Props) {
  const sf = storefrontFollowup || {};
  const [onHold, setOnHold] = useState(Boolean(sf.pipeline_on_hold));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOnHold(Boolean(sf.pipeline_on_hold));
  }, [productId, sf.pipeline_on_hold]);

  if (pipelineFocusActive) {
    return null;
  }

  const toggle = async () => {
    const next = !onHold;
    setBusy(true);
    try {
      const res = await api.updatePipelineProductFollowup(productId, { pipeline_on_hold: next });
      setOnHold(next);
      onPatch(productId, { storefront_followup: res.storefront_followup });
      toast.success(t(locale, next ? 'pipeline.pipelineHold.toastOn' : 'pipeline.pipelineHold.toastOff'));
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? `${t(locale, 'pipeline.pipelineHold.toastFailed')}: ${e.message}`
          : t(locale, 'pipeline.pipelineHold.toastFailed'),
      );
    } finally {
      setBusy(false);
    }
  };

  if (compact) {
    if (!onHold) return null;
    return (
      <button
        type="button"
        disabled={busy}
        onClick={(e) => {
          e.stopPropagation();
          void toggle();
        }}
        className={`inline-flex items-center gap-1 rounded-full border border-slate-500/50 bg-slate-950/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300 transition-colors hover:bg-slate-900/60 ${busy ? 'opacity-50 cursor-wait' : ''}`}
        title={t(locale, 'pipeline.pipelineHold.helpOn')}
      >
        <Pause className="h-3 w-3" aria-hidden />
        {t(locale, 'pipeline.pipelineHold.badge')}
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Pause className="h-4 w-4 text-slate-400 shrink-0" aria-hidden />
            <span className="text-sm font-medium text-white">{t(locale, 'pipeline.pipelineHold.title')}</span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {onHold ? t(locale, 'pipeline.pipelineHold.helpOn') : t(locale, 'pipeline.pipelineHold.helpOff')}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={onHold}
          disabled={busy}
          onClick={() => void toggle()}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            onHold ? 'bg-slate-500/80' : 'bg-emerald-600'
          } ${busy ? 'opacity-50 cursor-wait' : ''}`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
              onHold ? 'left-0.5' : 'left-[calc(100%-1.375rem)]'
            }`}
          />
        </button>
      </div>
    </div>
  );
}
