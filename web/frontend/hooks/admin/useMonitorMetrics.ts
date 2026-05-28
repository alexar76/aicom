'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { DashboardData } from '@/lib/api';
import {
  applyPublicStorefrontCount,
  bootDashboardData,
  createEmptyDashboardData,
  isPipelineMetricsReady,
  isSystemMetricsReady,
  writeAdminMetricsCacheIfValid,
} from '@/lib/adminMetricsCache';
import { connectAdminMetricsStream } from '@/lib/connectAdminMetricsStream';
import {
  loadAdminDashboardFull,
  loadAdminDashboardLayers,
} from '@/lib/loadAdminDashboardLayers';
import { fetchPublicStorefrontListableCount } from '@/lib/refreshStorefrontListableCount';

export type MonitorConnectionStatus = 'connecting' | 'connected' | 'error';

export function useMonitorMetrics() {
  const bootSnapshotRef = useRef(bootDashboardData());
  const bootReady = isPipelineMetricsReady(bootSnapshotRef.current);
  const [metrics, setMetrics] = useState<DashboardData | null>(() => bootSnapshotRef.current);
  const [paused, setPaused] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<MonitorConnectionStatus>('connecting');
  const [initialLoading, setInitialLoading] = useState(() => !bootReady);
  const [bootRefreshing, setBootRefreshing] = useState(() => bootReady);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const pipelineReady = metrics != null && isPipelineMetricsReady(metrics);
  const systemReady = metrics != null && isSystemMetricsReady(metrics);
  const agentsReady =
    metrics != null &&
    !metrics.dashboard_partial &&
    Object.keys(metrics.agent_metrics ?? {}).length > 0;
  const pipelineLoading = !pipelineReady && (initialLoading || bootRefreshing);
  const systemLoading = !systemReady && (initialLoading || bootRefreshing);

  const reloadMetrics = useCallback(async () => {
    setBootRefreshing(true);
    const { snapshot } = await loadAdminDashboardLayers();
    setMetrics(snapshot);
    setBootRefreshing(false);
    setInitialLoading(false);
    void loadAdminDashboardFull().then((full) => {
      if (full) setMetrics(full);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const { snapshot, pipelineCountsReady } = await loadAdminDashboardLayers();
      if (!cancelled) {
        setMetrics(snapshot);
        setInitialLoading(false);
        setBootRefreshing(false);
        if (!pipelineCountsReady && !isPipelineMetricsReady(snapshot)) {
          setMetrics(createEmptyDashboardData());
        }
      }
      if (!cancelled) {
        void loadAdminDashboardFull().then((full) => {
          if (!cancelled && full) setMetrics(full);
        });
        try {
          const vitrine = await fetchPublicStorefrontListableCount();
          if (!cancelled && vitrine !== null) {
            setMetrics((prev) =>
              prev
                ? applyPublicStorefrontCount(prev, vitrine)
                : prev,
            );
          }
        } catch {
          /* ignore */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (pipelineReady || initialLoading) return;
    const id = setInterval(() => {
      void loadAdminDashboardLayers().then(({ snapshot }) => setMetrics(snapshot));
    }, 12_000);
    return () => clearInterval(id);
  }, [pipelineReady, initialLoading]);

  useEffect(() => {
    let disconnect: (() => void) | undefined;
    const timer = setTimeout(() => {
      disconnect = connectAdminMetricsStream({
        onOpen: () => setConnectionStatus('connected'),
        onMessage: (data) => {
          if (pausedRef.current) return;
          if (data && typeof data === 'object') {
            writeAdminMetricsCacheIfValid(data);
            setMetrics(data as DashboardData);
            setInitialLoading(false);
          }
        },
        onError: () => setConnectionStatus('error'),
      });
      setConnectionStatus('connecting');
    }, 1500);

    return () => {
      clearTimeout(timer);
      disconnect?.();
    };
  }, []);

  return {
    metrics,
    paused,
    setPaused,
    connectionStatus,
    initialLoading,
    bootRefreshing,
    pipelineReady,
    pipelineLoading,
    systemReady,
    systemLoading,
    agentsReady,
    reloadMetrics,
  };
}
