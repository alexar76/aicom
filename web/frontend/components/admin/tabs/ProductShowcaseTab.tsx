'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Film, Loader2, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { type AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

function entryHasClip(entry: { clip?: string } | undefined): boolean {
  const clip = String(entry?.clip || '');
  return clip.endsWith('.webm') || clip.endsWith('.mp4');
}

export function ProductShowcaseTab({ locale }: { locale: AdminLocale }) {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [recording, setRecording] = useState(false);
  const [productId, setProductId] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getShowcaseGallery();
      setEntries(r.entries || []);
      return r.entries || [];
    } catch {
      setEntries([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const waitForCapture = (pid: string) => {
    stopPolling();
    const started = Date.now();
    const timeoutMs = 6 * 60 * 1000;
    const tick = async () => {
      if (Date.now() - started > timeoutMs) {
        stopPolling();
        setRecording(false);
        toast.error(t(locale, 'wow.showcaseFailed'));
        return;
      }
      const list = await load();
      const row = list.find((e: { product_id?: string }) => e?.product_id === pid);
      if (entryHasClip(row)) {
        stopPolling();
        setRecording(false);
        toast.success(t(locale, 'wow.showcaseDone'));
        return;
      }
      try {
        const st = await api.getProductShowcaseStatus(pid);
        if (st.status === 'failed') {
          stopPolling();
          setRecording(false);
          toast.error(`${t(locale, 'wow.showcaseFailed')}: ${st.error || st.status}`);
        } else if (st.status === 'done') {
          stopPolling();
          setRecording(false);
          toast.success(t(locale, 'wow.showcaseDone'));
        }
      } catch {
        /* ignore status poll errors */
      }
    };
    void tick();
    pollRef.current = setInterval(() => void tick(), 4000);
  };

  const enqueue = async () => {
    const pid = productId.trim();
    if (!pid) return;
    setRecording(true);
    try {
      const r = await api.enqueueProductShowcase(pid);
      if (r?.status === 'already_queued') {
        toast(t(locale, 'wow.showcaseAlreadyQueued'), { icon: '⏳' });
      } else {
        toast.success(t(locale, 'wow.showcaseQueued'));
      }
      void waitForCapture(pid);
    } catch (e: unknown) {
      setRecording(false);
      const msg = e instanceof Error ? e.message : t(locale, 'wow.showcaseFailed');
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Film className="h-5 w-5 text-pink-400" />
          {t(locale, 'tab.showcase')}
        </h2>
        <p className="text-xs text-gray-500 mt-1">{t(locale, 'wow.showcaseIntro')}</p>
      </div>

      <GlassCard className="p-4 flex flex-wrap gap-2 items-end">
        <label className="text-xs text-gray-400 flex flex-col gap-1 flex-1 min-w-[200px]">
          {t(locale, 'wow.showcaseProductId')}
          <input
            className="rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white"
            placeholder="prod-…"
            value={productId}
            disabled={recording}
            onChange={(e) => setProductId(e.target.value)}
          />
        </label>
        <Button disabled={recording || !productId.trim()} onClick={() => void enqueue()}>
          {recording ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {t(locale, 'wow.showcaseRecording')}
            </>
          ) : (
            t(locale, 'wow.showcaseRecord')
          )}
        </Button>
        <Button variant="secondary" disabled={recording} onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </GlassCard>

      {loading && !recording ? (
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mx-auto" />
      ) : entries.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">{t(locale, 'wow.showcaseEmpty')}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {entries.map((e) => (
            <GlassCard key={e.product_id} className="p-3 space-y-2">
              <p className="text-sm font-medium text-white truncate">{e.product_id}</p>
              <a
                href={e.preview_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-cyan-400 hover:underline"
              >
                {t(locale, 'wow.showcaseOpenPreview')}
              </a>
              {entryHasClip(e) ? (
                <video
                  src={`/docs/gallery/recordings/${e.clip}`}
                  className="w-full rounded-lg"
                  controls
                  muted
                  onError={(ev) => {
                    ev.currentTarget.style.display = 'none';
                  }}
                />
              ) : (
                <p className="text-[11px] text-gray-500">{e.clip || '—'}</p>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
