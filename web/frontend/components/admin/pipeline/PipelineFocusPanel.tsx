'use client';

import { useEffect, useMemo, useState } from 'react';
import { Crosshair, Pause } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { FilterSelect } from '@/components/admin/FilterControls';
import { t, tVars, type AdminLocale } from '@/lib/adminI18n';

type Props = {
  locale: AdminLocale;
  products: any[];
  onFocusApplied: () => void;
};

export function PipelineFocusPanel({ locale, products, onFocusApplied }: Props) {
  const [focusId, setFocusId] = useState<string | null>(null);
  const [suggestedId, setSuggestedId] = useState<string | null>(null);
  const [pausedCount, setPausedCount] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const inProgressOptions = useMemo(() => {
    const terminal = new Set(['COMPLETED', 'DEPLOYED_PRODUCTION', 'FAILED', 'CANCELLED']);
    const truncate = (text: string, max = 72) => {
      const s = String(text || '').trim();
      if (s.length <= max) return s;
      return `${s.slice(0, max - 1)}…`;
    };
    return products
      .filter((p) => !terminal.has(String(p?.state || '').toUpperCase()))
      .map((p) => {
        const spec = p?.spec || {};
        const rawName = spec?.product_name || p?.idea || p?.id;
        const name = truncate(String(rawName));
        const dp = p?.delivery_profile || spec?.delivery_profile || '';
        const fullName = String(rawName);
        return {
          id: String(p.id),
          label: `${name}${dp ? ` · ${dp}` : ''}`,
          title: fullName.length > name.length ? fullName : undefined,
          deliveryProfile: String(dp || ''),
        };
      })
      .sort((a, b) => {
        const weight = (dp: string) => (dp === 'full_software' ? 2 : dp ? 1 : 0);
        return weight(b.deliveryProfile) - weight(a.deliveryProfile) || a.label.localeCompare(b.label);
      });
  }, [products]);

  const refresh = async () => {
    setLoading(true);
    try {
      const status = await api.getPipelineFocusMode();
      setFocusId(status.focus_product_id);
      setSuggestedId(status.suggested_product_id);
      setPausedCount(status.paused_count);
      setActiveCount(status.active_count);
      if (status.focus_product_id) {
        setSelectedId(status.focus_product_id);
      } else if (status.suggested_product_id) {
        setSelectedId(status.suggested_product_id);
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [products.length]);

  const enableFocus = async (autoSelect: boolean) => {
    setBusy(true);
    try {
      const res = await api.setPipelineFocusMode({
        focus_product_id: autoSelect ? undefined : selectedId || undefined,
        auto_select: autoSelect,
        resume_factory: true,
      });
      setFocusId(res.focus_product_id);
      setPausedCount(res.paused_count);
      setActiveCount(res.active_count);
      toast.success(t(locale, 'pipeline.focus.toastEnabled'));
      onFocusApplied();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? `${t(locale, 'pipeline.focus.toastFailed')}: ${e.message}`
          : t(locale, 'pipeline.focus.toastFailed'),
      );
    } finally {
      setBusy(false);
    }
  };

  const clearFocus = async () => {
    setBusy(true);
    try {
      await api.setPipelineFocusMode({ clear_focus: true, resume_factory: false });
      setFocusId(null);
      setPausedCount(0);
      setActiveCount(products.length);
      toast.success(t(locale, 'pipeline.focus.toastDisabled'));
      onFocusApplied();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? `${t(locale, 'pipeline.focus.toastFailed')}: ${e.message}`
          : t(locale, 'pipeline.focus.toastFailed'),
      );
    } finally {
      setBusy(false);
    }
  };

  const active = Boolean(focusId);

  return (
    <div
      className={`rounded-xl border p-4 ${
        active ? 'border-indigo-500/40 bg-indigo-950/20' : 'border-white/10 bg-white/[0.03]'
      }`}
    >
      <div className="flex flex-col gap-4">
        <div className="w-full">
          <div className="flex flex-wrap items-center gap-2">
            <Crosshair className={`h-4 w-4 shrink-0 ${active ? 'text-indigo-300' : 'text-gray-400'}`} aria-hidden />
            <span className="text-sm font-medium text-white">{t(locale, 'pipeline.focus.title')}</span>
            {active ? (
              <Badge variant="info" className="text-[10px]">
                {t(locale, 'pipeline.focus.badge')}
              </Badge>
            ) : null}
            {active ? (
              <span className="text-[11px] text-gray-400">
                {tVars(locale, 'pipeline.focus.pausedCount', {
                  paused: pausedCount,
                  active: activeCount,
                })}
              </span>
            ) : null}
          </div>
          <p className="mt-2 max-w-3xl text-xs leading-relaxed text-gray-500">
            {active ? t(locale, 'pipeline.focus.helpActive') : t(locale, 'pipeline.focus.helpInactive')}
          </p>
          {active && focusId ? (
            <p className="mt-1 font-mono text-[11px] text-indigo-200/90 break-all">{focusId}</p>
          ) : suggestedId && !loading ? (
            <p className="mt-1 text-[11px] text-gray-500">
              {t(locale, 'pipeline.focus.autoSelect')}: <span className="font-mono text-gray-400">{suggestedId}</span>
            </p>
          ) : null}
        </div>

        <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          {!active ? (
            <>
              <FilterSelect
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full min-w-0 max-w-full sm:max-w-md px-3 py-2 text-sm"
                disabled={busy || inProgressOptions.length === 0}
              >
                <option value="">{t(locale, 'pipeline.focus.selectLabel')}</option>
                {inProgressOptions.map((opt) => (
                  <option key={opt.id} value={opt.id} title={opt.title}>
                    {opt.label}
                  </option>
                ))}
              </FilterSelect>
              <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                disabled={busy || (!selectedId && !suggestedId)}
                onClick={() => void enableFocus(false)}
              >
                {t(locale, 'pipeline.focus.enable')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={busy || !suggestedId}
                onClick={() => void enableFocus(true)}
              >
                {t(locale, 'pipeline.focus.autoSelect')}
              </Button>
              </div>
            </>
          ) : (
            <>
              <div className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-950/30 px-2 py-1 text-[10px] text-amber-200">
                <Pause className="h-3 w-3" aria-hidden />
                {tVars(locale, 'pipeline.focus.pausedCount', { paused: pausedCount, active: activeCount })}
              </div>
              <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void clearFocus()}>
                {t(locale, 'pipeline.focus.disable')}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
