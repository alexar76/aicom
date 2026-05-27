'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import api, { type DashboardData } from '@/lib/api';
import {
  applyPublicStorefrontCount,
  createEmptyDashboardData,
  isPipelineMetricsReady,
  mergeDashboardQuick,
  readAdminMetricsCache,
  writeAdminMetricsCache,
  writeAdminMetricsCacheIfValid,
} from '@/lib/adminMetricsCache';
import { connectAdminMetricsStream } from '@/lib/connectAdminMetricsStream';
import { fetchPublicStorefrontListableCount } from '@/lib/refreshStorefrontListableCount';

export type MonitorConnectionStatus = 'connecting' | 'connected' | 'error';

async function loadDashboardLayers(
  setMetrics: Dispatch<SetStateAction<DashboardData | null>>,
): Promise<void> {
  try {
    const quick = await api.getDashboard(true);
    setMetrics((prev) => (prev ? mergeDashboardQuick(prev, quick) : quick));
  } catch {
    /* stream / retry may still update */
  }
  try {
    const full = await api.getDashboard(false);
    setMetrics(full);
    writeAdminMetricsCache(full);
  } catch {
    /* quick or cache may still update */
  }
  try {
    const vitrine = await fetchPublicStorefrontListableCount();
    if (vitrine !== null) {
      setMetrics((prev) =>
        prev
          ? applyPublicStorefrontCount(prev, vitrine)
          : applyPublicStorefrontCount(createEmptyDashboardData(), vitrine),
      );
    }
  } catch {
    /* ignore */
  }
}

export function useMonitorMetrics() {
  const bootSnapshotRef = useRef(readAdminMetricsCache());
  const [metrics, setMetrics] = useState<DashboardData | null>(() => bootSnapshotRef.current ?? null);
  const [paused, setPaused] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<MonitorConnectionStatus>('connecting');
  const [initialLoading, setInitialLoading] = useState(() => bootSnapshotRef.current == null);
  const [bootRefreshing, setBootRefreshing] = useState(() => bootSnapshotRef.current != null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const pipelineReady = metrics != null && isPipelineMetricsReady(metrics);
  const agentsReady =
    metrics != null &&
    !metrics.dashboard_partial &&
    Object.keys(metrics.agent_metrics ?? {}).length > 0;

  const reloadMetrics = useCallback(async () => {
    setBootRefreshing(true);
    await loadDashboardLayers(setMetrics);
    setBootRefreshing(false);
    setInitialLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await loadDashboardLayers(setMetrics);
      if (!cancelled) {
        setInitialLoading(false);
        setBootRefreshing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (pipelineReady || initialLoading) return;
    const id = setInterval(() => {
      void loadDashboardLayers(setMetrics);
    }, 12_000);
    return () => clearInterval(id);
  }, [pipelineReady, initialLoading]);

  useEffect(() => {
    const disconnect = connectAdminMetricsStream({
      onOpen: () => setConnectionStatus('connected'),
      onMessage: (data) => {
        if (pausedRef.current) return;
        if (data && typeof data === 'object') {
          setMetrics(data as DashboardData);
          writeAdminMetricsCacheIfValid(data);
          setInitialLoading(false);
        }
      },
      onError: () => setConnectionStatus('error'),
    });
    setConnectionStatus('connecting');
    return disconnect;
  }, []);

  return {
    metrics,
    paused,
    setPaused,
    connectionStatus,
    initialLoading,
    bootRefreshing,
    pipelineReady,
    agentsReady,
    reloadMetrics,
  };
}
