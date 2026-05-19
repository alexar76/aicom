'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Clock, GitBranch, Loader2, Play } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { type AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

type ReplayFrame = {
  index: number;
  agent_type?: string;
  status?: string;
  input_preview?: string;
  output_preview?: string;
  cost_usd?: number;
  cumulative_cost_usd?: number;
  duration_sec?: number | null;
  error?: string | null;
};

export function TimeTravelReplayTab({ locale }: { locale: AdminLocale }) {
  const [products, setProducts] = useState<any[]>([]);
  const [productId, setProductId] = useState('');
  const [timeline, setTimeline] = useState<{ frames?: ReplayFrame[]; product_title?: string; total_cost_usd?: number } | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [forkNotes, setForkNotes] = useState('');
  const [forking, setForking] = useState(false);

  useEffect(() => {
    api.getPipelineProducts(40, 0, 'newest', true).then((r) => {
      const rows = r.products || [];
      setProducts(rows);
      if (rows[0]?.id) setProductId(String(rows[0].id));
    }).catch(() => setProducts([]));
  }, []);

  const loadTimeline = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    try {
      const data = await api.getReplayTimeline(productId);
      setTimeline(data);
      setFrameIdx(Math.max(0, (data.frames?.length || 1) - 1));
    } catch {
      toast.error('Failed to load replay timeline');
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    if (productId) void loadTimeline();
  }, [productId, loadTimeline]);

  const frame = timeline?.frames?.[frameIdx];
  const maxIdx = Math.max(0, (timeline?.frames?.length || 1) - 1);

  const fork = async () => {
    if (!productId || !frame) return;
    setForking(true);
    try {
      const r = await api.forkReplayFrom(productId, {
        frame_index: frame.index,
        operator_notes: forkNotes,
      });
      toast.success(`Fork queued: ${r.task_id}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Fork failed');
    } finally {
      setForking(false);
    }
  };

  const agentHighlight = useMemo(() => new Set(frame?.agent_type ? [frame.agent_type] : []), [frame]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Clock className="h-5 w-5 text-violet-400" />
          {t(locale, 'tab.timeTravel')}
        </h2>
        <p className="text-xs text-gray-500 mt-1">{t(locale, 'wow.timeTravelIntro')}</p>
      </div>

      <GlassCard className="p-4 flex flex-wrap gap-3 items-end">
        <label className="text-xs text-gray-400 flex flex-col gap-1 min-w-[220px]">
          Product
          <select
            className="rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>{String(p.idea || p.id).slice(0, 60)}</option>
            ))}
          </select>
        </label>
        <Button variant="secondary" onClick={() => void loadTimeline()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Reload
        </Button>
      </GlassCard>

      {loading && !timeline ? (
        <div className="flex h-40 items-center justify-center text-gray-500">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
        </div>
      ) : timeline ? (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          <GlassCard className="p-4 space-y-3">
            <p className="text-sm font-medium text-white truncate">{timeline.product_title}</p>
            <input
              type="range"
              min={0}
              max={maxIdx}
              value={frameIdx}
              onChange={(e) => setFrameIdx(Number(e.target.value))}
              className="w-full accent-indigo-500"
            />
            <p className="text-xs text-gray-500">
              Frame {frameIdx + 1} / {timeline.frames?.length || 0}
              {timeline.total_cost_usd != null ? ` · $${timeline.total_cost_usd.toFixed(4)} total` : ''}
            </p>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {(timeline.frames || []).map((f, i) => (
                <button
                  key={f.index}
                  type="button"
                  onClick={() => setFrameIdx(i)}
                  className={`w-full text-left text-[11px] px-2 py-1 rounded ${
                    i === frameIdx ? 'bg-indigo-500/30 text-white' : 'text-gray-500 hover:bg-white/5'
                  }`}
                >
                  {f.agent_type} · {f.status}
                </button>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="p-4 space-y-3">
            {frame ? (
              <>
                <motion.div
                  key={frame.index}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-wrap gap-2"
                >
                  <span className="text-xs px-2 py-1 rounded-full bg-indigo-500/20 text-indigo-200">
                    {frame.agent_type}
                  </span>
                  <span className="text-xs px-2 py-1 rounded-full bg-white/5 text-gray-400">{frame.status}</span>
                  {frame.duration_sec != null ? (
                    <span className="text-xs text-gray-500">{frame.duration_sec}s</span>
                  ) : null}
                  {frame.cost_usd != null ? (
                    <span className="text-xs text-emerald-400">${frame.cost_usd.toFixed(4)}</span>
                  ) : null}
                </motion.div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-1">Input</p>
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-black/30 rounded-lg p-3 max-h-32 overflow-auto">
                    {frame.input_preview || '—'}
                  </pre>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-gray-600 mb-1">Output</p>
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-black/30 rounded-lg p-3 max-h-40 overflow-auto">
                    {frame.output_preview || frame.error || '—'}
                  </pre>
                </div>
                <div className="border-t border-white/10 pt-3 space-y-2">
                  <p className="text-xs text-gray-400 flex items-center gap-1">
                    <GitBranch className="h-3.5 w-3.5" /> Fork from here
                  </p>
                  <textarea
                    className="w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-xs text-white min-h-[72px]"
                    placeholder="Instructions for alternate branch…"
                    value={forkNotes}
                    onChange={(e) => setForkNotes(e.target.value)}
                  />
                  <Button onClick={() => void fork()} disabled={forking}>
                    {forking ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Fork from frame {frame.index}
                  </Button>
                </div>
              </>
            ) : null}
            <div className="flex flex-wrap gap-1 pt-2">
              {['analyst', 'pm', 'developer', 'qa', 'devops'].map((a) => (
                <span
                  key={a}
                  className={`text-[10px] px-2 py-0.5 rounded ${agentHighlight.has(a) ? 'bg-cyan-500/30 text-cyan-100' : 'bg-white/5 text-gray-600'}`}
                >
                  {a}
                </span>
              ))}
            </div>
          </GlassCard>
        </div>
      ) : null}
    </div>
  );
}
