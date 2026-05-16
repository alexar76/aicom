'use client';

import { useEffect, useRef, useState } from 'react';
import api from '@/lib/api';
import {
  readAdminMetricsCache,
  writeAdminMetricsCache,
  writeAdminMetricsCacheIfValid,
} from '@/lib/adminMetricsCache';

export type MonitorConnectionStatus = 'connecting' | 'connected' | 'error';

export function useMonitorMetrics() {
  const bootSnapshotRef = useRef(readAdminMetricsCache());
  const [metrics, setMetrics] = useState<any>(() => bootSnapshotRef.current ?? null);
  const [paused, setPaused] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<MonitorConnectionStatus>('connecting');
  const [initialLoading, setInitialLoading] = useState(() => bootSnapshotRef.current == null);
  const [bootRefreshing, setBootRefreshing] = useState(() => bootSnapshotRef.current != null);

  useEffect(() => {
    api
      .getDashboard()
      .then((data) => {
        setMetrics(data);
        writeAdminMetricsCache(data);
        setInitialLoading(false);
        setBootRefreshing(false);
      })
      .catch(() => {
        setInitialLoading(false);
        setBootRefreshing(false);
      });
  }, []);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      setConnectionStatus('connecting');
      try {
        eventSource = new EventSource('/api/admin/metrics/stream');
        eventSource.onopen = () => setConnectionStatus('connected');
        eventSource.onmessage = (event) => {
          if (paused) return;
          try {
            const data = JSON.parse(event.data);
            setMetrics(data);
            writeAdminMetricsCacheIfValid(data);
          } catch {
            /* ignore */
          }
        };
        eventSource.addEventListener('error', () => {
          setConnectionStatus('error');
          eventSource?.close();
          reconnectTimer = setTimeout(connect, 5000);
        });
      } catch {
        setConnectionStatus('error');
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();
    return () => {
      eventSource?.close();
      clearTimeout(reconnectTimer);
    };
  }, [paused]);

  return {
    metrics,
    paused,
    setPaused,
    connectionStatus,
    initialLoading,
    bootRefreshing,
  };
}
