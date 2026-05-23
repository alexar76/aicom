import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPricing, pricingSseUrl, pricingWsUrl } from '../lib/api';
import type { Chain, ConnectionMode, PricingSnapshot } from '../lib/types';

type HistoryMap = Record<string, number[]>;

const MAX_HISTORY = 48;

function pushHistory(prev: HistoryMap, snap: PricingSnapshot): HistoryMap {
  const next = { ...prev };
  for (const idx of snap.indices) {
    const key = idx.listing_id;
    const arr = [...(next[key] ?? []), idx.level];
    next[key] = arr.slice(-MAX_HISTORY);
  }
  return next;
}

export function usePricingStream(chain: Chain) {
  const [snapshot, setSnapshot] = useState<PricingSnapshot | null>(null);
  const [history, setHistory] = useState<HistoryMap>({});
  const [mode, setMode] = useState<ConnectionMode>('offline');
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<number | null>(null);

  const applySnap = useCallback((snap: PricingSnapshot, ms: number) => {
    setSnapshot(snap);
    setHistory((h) => pushHistory(h, snap));
    setLatencyMs(ms);
    setError(null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const cleanup = () => {
      wsRef.current?.close();
      wsRef.current = null;
      esRef.current?.close();
      esRef.current = null;
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };

    const startPolling = (refreshMs: number) => {
      if (cancelled) return;
      setMode('polling');
      const tick = async () => {
        const t0 = performance.now();
        try {
          const snap = await fetchPricing(chain);
          if (!cancelled) applySnap(snap, Math.round(performance.now() - t0));
        } catch (e) {
          if (!cancelled) setError(e instanceof Error ? e.message : 'poll failed');
        }
      };
      void tick();
      pollRef.current = window.setInterval(tick, Math.max(refreshMs, 2000));
    };

    const startSse = () => {
      if (cancelled) return;
      setMode('sse');
      const es = new EventSource(pricingSseUrl(chain));
      esRef.current = es;
      es.onmessage = (ev) => {
        const t0 = performance.now();
        try {
          const snap = JSON.parse(ev.data) as PricingSnapshot;
          applySnap(snap, Math.round(performance.now() - t0));
        } catch {
          setError('invalid SSE payload');
        }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!cancelled) startPolling(5000);
      };
    };

    const startWs = () => {
      if (cancelled) return;
      setMode('websocket');
      const ws = new WebSocket(pricingWsUrl(chain));
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        const t0 = performance.now();
        try {
          const snap = JSON.parse(ev.data) as PricingSnapshot;
          applySnap(snap, Math.round(performance.now() - t0));
        } catch {
          setError('invalid WebSocket payload');
        }
      };
      ws.onerror = () => {
        ws.close();
        wsRef.current = null;
        if (!cancelled) startSse();
      };
      ws.onclose = () => {
        if (!cancelled && !wsRef.current) startSse();
      };
    };

    cleanup();
    setMode('offline');
    startWs();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [chain, applySnap]);

  return { snapshot, history, mode, error, latencyMs };
}
