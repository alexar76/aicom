'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, RefreshCw, RotateCcw, Power, PowerOff, Radio } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api, { type CircuitBreakerSnapshot, type CircuitBreakerRow } from '@/lib/api';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

function stateColor(state: string): string {
  switch (state) {
    case 'open':
      return 'bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.65)]';
    case 'half_open':
      return 'bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.55)] animate-pulse';
    default:
      return 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.45)]';
  }
}

function stateLabel(locale: AdminLocale, state: string): string {
  if (state === 'open') return t(locale, 'providers.circuit.stateOpen');
  if (state === 'half_open') return t(locale, 'providers.circuit.stateHalfOpen');
  return t(locale, 'providers.circuit.stateClosed');
}

function formatSec(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (v < 60) return `${v.toFixed(1)}s`;
  return `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`;
}

export function CircuitBreakerPanel({ locale }: { locale: AdminLocale }) {
  const [snapshot, setSnapshot] = useState<CircuitBreakerSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getProviderCircuits();
      setSnapshot(data);
    } catch (e) {
      console.error('circuit snapshot', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!live || typeof window === 'undefined') return;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/api/admin/ws/metrics`);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload?.circuit_breakers) {
          setSnapshot(payload.circuit_breakers as CircuitBreakerSnapshot);
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      ws.close();
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [live]);

  const rows = useMemo(() => {
    const providers = snapshot?.providers ?? {};
    return Object.entries(providers).sort(([a], [b]) => a.localeCompare(b));
  }, [snapshot]);

  const runAction = async (
    name: string,
    action: 'open' | 'close' | 'reset',
    fn: (n: string) => Promise<unknown>,
  ) => {
    setActing(`${name}:${action}`);
    try {
      await fn(name);
      toast.success(tVars(locale, 'providers.circuit.actionDone', { provider: name, action }));
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    } finally {
      setActing(null);
    }
  };

  const cfg = snapshot?.config;

  return (
    <GlassCard className="p-4 border border-violet-500/25 bg-violet-950/20">
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
        <motion.div
          className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          layout
        >
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-violet-400" />
              {t(locale, 'providers.circuit.title')}
            </h3>
            <p className="text-xs text-gray-400 mt-1 max-w-2xl">{t(locale, 'providers.circuit.subtitle')}</p>
            {cfg && (
              <p className="text-[10px] text-slate-500 mt-1 font-mono">
                {tVars(locale, 'providers.circuit.policy', {
                  threshold: cfg.failure_threshold,
                  window: cfg.failure_window_sec,
                  cooldown: cfg.open_duration_sec,
                })}
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setLive((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs border transition-colors ${
                live
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                  : 'border-white/10 bg-white/5 text-gray-400'
              }`}
            >
              <Radio className={`w-3.5 h-3.5 ${live ? 'animate-pulse' : ''}`} />
              {live ? t(locale, 'providers.circuit.liveOn') : t(locale, 'providers.circuit.liveOff')}
            </button>
            <Button variant="secondary" size="sm" onClick={() => load()} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
              {t(locale, 'providers.btn.refresh')}
            </Button>
          </div>
        </motion.div>

        {loading && rows.length === 0 ? (
          <p className="text-xs text-gray-500 py-4 text-center">{t(locale, 'providers.circuit.loading')}</p>
        ) : rows.length === 0 ? (
          <p className="text-xs text-gray-500 py-4 text-center">{t(locale, 'providers.circuit.empty')}</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <AnimatePresence mode="popLayout">
              {rows.map(([name, row]) => (
                <CircuitCard
                  key={name}
                  locale={locale}
                  name={name}
                  row={row}
                  acting={acting}
                  onOpen={() => runAction(name, 'open', api.circuitForceOpen.bind(api))}
                  onClose={() => runAction(name, 'close', api.circuitForceClose.bind(api))}
                  onReset={() => runAction(name, 'reset', api.circuitReset.bind(api))}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </motion.div>
    </GlassCard>
  );
}

function CircuitCard({
  locale,
  name,
  row,
  acting,
  onOpen,
  onClose,
  onReset,
}: {
  locale: AdminLocale;
  name: string;
  row: CircuitBreakerRow;
  acting: string | null;
  onOpen: () => void;
  onClose: () => void;
  onReset: () => void;
}) {
  const st = row.state || 'closed';
  const busyOpen = acting === `${name}:open`;
  const busyClose = acting === `${name}:close`;
  const busyReset = acting === `${name}:reset`;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="rounded-xl border border-white/10 bg-black/30 p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <motion.div className="flex items-center gap-2 min-w-0" layout="position">
          <span
            className={`h-3 w-3 shrink-0 rounded-full ${stateColor(st)}`}
            title={stateLabel(locale, st)}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{name}</p>
            <p className="text-[10px] uppercase tracking-wide text-gray-500">{stateLabel(locale, st)}</p>
          </div>
        </motion.div>
        {row.manual_override && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/25">
            {row.manual_override}
          </span>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
        <div>
          <dt className="text-gray-500">{t(locale, 'providers.circuit.failuresWindow')}</dt>
          <dd className="text-gray-200 tabular-nums">
            {row.failure_count_window}/{row.failure_threshold}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">{t(locale, 'providers.circuit.recovery')}</dt>
          <dd className="text-gray-200 tabular-nums">{formatSec(row.last_recovery_duration_sec)}</dd>
        </div>
        {st === 'open' && row.seconds_until_half_open != null && (
          <div className="col-span-2">
            <dt className="text-gray-500">{t(locale, 'providers.circuit.untilHalfOpen')}</dt>
            <dd className="text-amber-200/90 tabular-nums">{formatSec(row.seconds_until_half_open)}</dd>
          </div>
        )}
        <div className="col-span-2">
          <dt className="text-gray-500">{t(locale, 'providers.circuit.lastError')}</dt>
          <dd className="text-gray-400 truncate font-mono" title={row.last_error}>
            {row.last_error || '—'}
          </dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap gap-1">
        <button
          type="button"
          disabled={busyOpen || busyClose || busyReset}
          onClick={onOpen}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 disabled:opacity-40"
          title={t(locale, 'providers.circuit.forceOpen')}
        >
          <PowerOff className="w-3 h-3" />
          OPEN
        </button>
        <button
          type="button"
          disabled={busyOpen || busyClose || busyReset}
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-40"
          title={t(locale, 'providers.circuit.forceClose')}
        >
          <Power className="w-3 h-3" />
          CLOSE
        </button>
        <button
          type="button"
          disabled={busyOpen || busyClose || busyReset}
          onClick={onReset}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] bg-white/5 text-gray-300 hover:bg-white/10 disabled:opacity-40"
          title={t(locale, 'providers.circuit.reset')}
        >
          <RotateCcw className="w-3 h-3" />
          RESET
        </button>
      </div>
    </motion.div>
  );
}
