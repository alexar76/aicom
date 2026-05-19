'use client';

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type Node,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { motion } from 'framer-motion';
import { Loader2, Radio, Zap } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import api from '@/lib/api';
import {
  readFactoryFloorCache,
  writeFactoryFloorCache,
  type FactoryFloorNode,
  type FactoryFloorPayload,
} from '@/lib/factoryFloorCache';
import { type AdminLocale, t } from '@/lib/adminI18n';

const STATUS_COLOR: Record<string, string> = {
  running: '#22d3ee',
  thinking: '#a78bfa',
  idle: '#475569',
};

function AgentNode({ data }: { data: FactoryFloorNode & { shake?: boolean } }) {
  const color = STATUS_COLOR[data.status] || STATUS_COLOR.idle;
  return (
    <motion.div
      animate={data.circuit_tripped || data.shake ? { x: [0, -4, 4, -3, 3, 0] } : {}}
      transition={{ duration: 0.45 }}
      className="min-w-[168px] max-w-[220px] rounded-xl border px-3 py-2 shadow-lg"
      style={{
        borderColor: data.circuit_tripped ? '#f87171' : color,
        background: 'linear-gradient(145deg, rgba(15,23,42,0.95), rgba(30,27,75,0.85))',
        boxShadow: data.status === 'running' ? `0 0 18px ${color}55` : undefined,
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-white truncate">{data.label}</span>
        <span
          className="h-2 w-2 shrink-0 rounded-full animate-pulse"
          style={{ backgroundColor: data.circuit_tripped ? '#ef4444' : color }}
        />
      </div>
      <p className="mt-1 text-[10px] text-slate-400 truncate">{data.provider || '—'} · {data.model || '—'}</p>
      {data.prompt_line ? (
        <p className="mt-1 text-[10px] text-indigo-200/90 line-clamp-2">{data.prompt_line}</p>
      ) : null}
      <div className="mt-1 flex gap-2 text-[10px] text-slate-500">
        {data.latency_ms != null ? <span>{Math.round(data.latency_ms)}ms</span> : null}
        {data.cost_usd != null ? <span>${Number(data.cost_usd).toFixed(4)}</span> : null}
      </div>
    </motion.div>
  );
}

const nodeTypes = { agent: AgentNode };

type LivePhase = 'cached' | 'fetching' | 'live' | 'error';

function applyFloorPayload(floor: FactoryFloorPayload | null | undefined): FactoryFloorPayload | null {
  if (!floor?.nodes?.length) return null;
  writeFactoryFloorCache(floor);
  return floor;
}

function useFactoryFloorLive(
  onFloor: (floor: FactoryFloorPayload) => void,
  onPhase: (phase: LivePhase) => void,
  hasCachedFloor: boolean,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const fetchedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let wsRetryTimer: number | undefined;
    let sseRetryTimer: number | undefined;

    const applyMetrics = (payload: Record<string, unknown>) => {
      const ff = applyFloorPayload(payload.factory_floor as FactoryFloorPayload | undefined);
      if (ff) {
        onFloor(ff);
        onPhase('live');
        return true;
      }
      return false;
    };

    const fetchOnce = async () => {
      if (fetchedRef.current) return;
      fetchedRef.current = true;
      onPhase('fetching');
      try {
        const data = await api.getDashboard(false);
        if (cancelled) return;
        if (!applyMetrics(data as unknown as Record<string, unknown>)) {
          onPhase('error');
        }
      } catch {
        if (!cancelled) onPhase('error');
      }
    };

    void fetchOnce();

    if (typeof window === 'undefined') {
      return () => {
        cancelled = true;
      };
    }

    const connectSse = () => {
      if (cancelled) return;
      sseRef.current?.close();
      const es = new EventSource('/api/admin/metrics/stream');
      sseRef.current = es;
      es.onopen = () => {
        if (!cancelled) onPhase('live');
      };
      es.onmessage = (ev) => {
        try {
          applyMetrics(JSON.parse(ev.data) as Record<string, unknown>);
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        es.close();
        if (!cancelled) {
          onPhase(hasCachedFloor ? 'cached' : 'error');
          sseRetryTimer = window.setTimeout(connectSse, 5000);
        }
      };
    };

    connectSse();

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = localStorage.getItem('admin_token');
    const url = `${proto}//${window.location.host}/api/admin/ws/metrics`;

    const connectWs = () => {
      if (cancelled) return;
      wsRef.current?.close();
      const ws = token ? new WebSocket(url, ['Bearer', token]) : new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => onPhase('live');
      ws.onmessage = (ev) => {
        try {
          applyMetrics(JSON.parse(ev.data) as Record<string, unknown>);
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        ws.close();
        if (!cancelled) onPhase(hasCachedFloor ? 'cached' : 'error');
      };
      ws.onclose = () => {
        if (!cancelled) wsRetryTimer = window.setTimeout(connectWs, 4000);
      };
    };

    connectWs();

    return () => {
      cancelled = true;
      if (wsRetryTimer) window.clearTimeout(wsRetryTimer);
      if (sseRetryTimer) window.clearTimeout(sseRetryTimer);
      wsRef.current?.close();
      wsRef.current = null;
      sseRef.current?.close();
      sseRef.current = null;
    };
  }, [onFloor, onPhase, hasCachedFloor]);
}

export function FactoryFloorTab({ locale }: { locale: AdminLocale }) {
  const bootRef = useRef(readFactoryFloorCache());
  const hadCacheOnMount = bootRef.current != null;

  const [floor, setFloor] = useState<FactoryFloorPayload | null>(() => bootRef.current);
  const [livePhase, setLivePhase] = useState<LivePhase>(() => (hadCacheOnMount ? 'cached' : 'fetching'));

  useLayoutEffect(() => {
    const cached = readFactoryFloorCache();
    if (cached) {
      setFloor(cached);
      setLivePhase('cached');
    }
  }, []);

  const onFloor = useCallback((next: FactoryFloorPayload) => {
    setFloor(next);
  }, []);

  const onPhase = useCallback((phase: LivePhase) => {
    setLivePhase((prev) => {
      if (prev === 'live' && phase === 'fetching') return prev;
      return phase;
    });
  }, []);

  useFactoryFloorLive(onFloor, onPhase, hadCacheOnMount);

  const { flowNodes, flowEdges } = useMemo(() => {
    const agents = floor?.nodes || [];
    const n: Node[] = agents.map((a, i) => ({
      id: a.id,
      type: 'agent',
      position: { x: (i % 4) * 240, y: Math.floor(i / 4) * 130 },
      data: { ...a, shake: a.circuit_tripped },
    }));
    const hot = new Set((floor?.hot_edges || []).map((e) => `${e.from}->${e.to}`));
    const e: Edge[] = (floor?.edges || []).map((edge, idx) => ({
      id: `e-${edge.from}-${edge.to}-${idx}`,
      source: edge.from,
      target: edge.to,
      animated: hot.has(`${edge.from}->${edge.to}`),
      style: {
        stroke: hot.has(`${edge.from}->${edge.to}`) ? '#22d3ee' : '#334155',
        strokeWidth: hot.has(`${edge.from}->${edge.to}`) ? 2.5 : 1.2,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' },
    }));
    return { flowNodes: n, flowEdges: e };
  }, [floor]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges, setNodes, setEdges]);

  const syncing = livePhase === 'cached' || livePhase === 'fetching';
  const connectionLabel =
    livePhase === 'live'
      ? t(locale, 'wow.factoryFloorLive')
      : livePhase === 'error'
        ? hadCacheOnMount
          ? t(locale, 'wow.factoryFloorStale')
          : t(locale, 'wow.factoryFloorLoadFailed')
        : livePhase === 'cached'
          ? t(locale, 'wow.factoryFloorStale')
          : t(locale, 'wow.factoryFloorSyncing');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Zap className="h-5 w-5 text-cyan-400" />
            {t(locale, 'tab.factoryFloor')}
          </h2>
          <p className="text-xs text-gray-500 mt-1">{t(locale, 'wow.factoryFloorIntro')}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Radio
            className={`h-3.5 w-3.5 ${
              livePhase === 'live' ? 'text-emerald-400' : livePhase === 'error' ? 'text-rose-400' : 'text-amber-400'
            }`}
          />
          {connectionLabel}
          {floor?.running_count != null ? <span>· {floor.running_count} active</span> : null}
        </div>
      </div>

      {syncing && floor ? (
        <p className="flex items-center gap-2 text-xs text-indigo-200/80" aria-live="polite">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          {hadCacheOnMount ? t(locale, 'wow.factoryFloorCachedSync') : t(locale, 'wow.factoryFloorFirstLoad')}
        </p>
      ) : null}

      {!floor ? (
        <div className="flex h-64 items-center justify-center text-gray-500">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mr-2" />
          {t(locale, 'common.loading')}
        </div>
      ) : (
        <GlassCard
          className={`h-[min(72vh,720px)] p-0 overflow-hidden border-indigo-500/20 transition-opacity ${
            syncing ? 'opacity-95' : 'opacity-100'
          }`}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={20} />
            <MiniMap nodeColor={(n) => STATUS_COLOR[(n.data as FactoryFloorNode)?.status] || '#475569'} />
            <Controls />
          </ReactFlow>
        </GlassCard>
      )}

      {(floor?.open_circuits?.length || 0) > 0 ? (
        <p className="text-xs text-rose-400">
          Circuit open: {floor?.open_circuits?.join(', ')}
        </p>
      ) : null}
    </div>
  );
}
