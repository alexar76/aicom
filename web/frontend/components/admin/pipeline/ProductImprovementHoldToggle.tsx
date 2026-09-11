'use client';

import { useEffect, useState } from 'react';
import { Pause } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { t, type AdminLocale } from '@/lib/adminI18n';

type Props = {
  locale: AdminLocale;
  productId: string;
  storefrontFollowup?: Record<string, unknown> | null;
  onPatch: (productId: string, patch: Record<string, unknown>) => void;
  compact?: boolean;
};

export function ProductImprovementHoldToggle({
  locale,
  productId,
  storefrontFollowup,
  onPatch,
  compact = false,
}: Props) {
  const sf = storefrontFollowup || {};
  const [onHold, setOnHold] = useState(Boolean(sf.improvement_on_hold));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOnHold(Boolean(sf.improvement_on_hold));
  }, [productId, sf.improvement_on_hold]);

  const toggle = async () => {
    const next = !onHold;
    setBusy(true);
    try {
      const res = await api.updatePipelineProductFollowup(productId, { improvement_on_hold: next });
      setOnHold(next);
      onPatch(productId, { storefront_followup: res.storefront_followup });
      toast.success(t(locale, next ? 'pipeline.improvementHold.toastOn' : 'pipeline.improvementHold.toastOff'));
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? `${t(locale, 'pipeline.improvementHold.toastFailed')}: ${e.message}`
          : t(locale, 'pipeline.improvementHold.toastFailed'),
      );
    } finally {
      setBusy(false);
    }
  };

  if (compact) {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={(e) => {
          e.stopPropagation();
          void toggle();
        }}
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition-colors ${
          onHold
            ? 'border-amber-500/50 bg-amber-950/50 text-amber-200 hover:bg-amber-900/60'
            : 'border-white/15 bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200'
        } ${busy ? 'opacity-50 cursor-wait' : ''}`}
        title={onHold ? t(locale, 'pipeline.improvementHold.helpOn') : t(locale, 'pipeline.improvementHold.helpOff')}
      >
        <Pause className="h-3 w-3" aria-hidden />
        {t(locale, 'pipeline.improvementHold.badge')}
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Pause className="h-4 w-4 text-amber-400 shrink-0" aria-hidden />
            <span className="text-sm font-medium text-white">{t(locale, 'pipeline.improvementHold.title')}</span>
            {onHold ? (
              <Badge variant="warning" className="text-[10px]">
                {t(locale, 'pipeline.improvementHold.statusOn')}
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {onHold ? t(locale, 'pipeline.improvementHold.helpOn') : t(locale, 'pipeline.improvementHold.helpOff')}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`text-xs font-medium ${onHold ? 'text-amber-300' : 'text-emerald-300'}`}>
            {onHold
              ? t(locale, 'pipeline.improvementHold.statusOn')
              : t(locale, 'pipeline.improvementHold.statusOff')}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={onHold}
            disabled={busy}
            onClick={() => void toggle()}
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
              onHold ? 'bg-amber-500/80' : 'bg-emerald-600'
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
    </div>
  );
}
