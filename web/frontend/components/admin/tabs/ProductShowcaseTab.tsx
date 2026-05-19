'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Film, Loader2, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { type AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

export function ProductShowcaseTab({ locale }: { locale: AdminLocale }) {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [productId, setProductId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getShowcaseGallery();
      setEntries(r.entries || []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const enqueue = async () => {
    if (!productId.trim()) return;
    try {
      await api.enqueueProductShowcase(productId.trim());
      toast.success('Showcase queued');
      await load();
    } catch {
      toast.error('Enqueue failed');
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
          Product ID
          <input
            className="rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white"
            placeholder="prod-…"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
          />
        </label>
        <Button onClick={() => void enqueue()}>Record showcase</Button>
        <Button variant="secondary" onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </GlassCard>

      {loading ? (
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mx-auto" />
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
                Open preview
              </a>
              {String(e.clip || '').endsWith('.webm') ? (
                <video src={`/docs/gallery/recordings/${e.clip}`} className="w-full rounded-lg" controls muted />
              ) : (
                <p className="text-[11px] text-gray-500">{e.clip}</p>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
