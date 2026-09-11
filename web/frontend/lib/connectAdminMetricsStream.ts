/**
 * Live admin metrics stream — WebSocket when Bearer token exists (EventSource cannot set headers).
 * Falls back to SSE for cookie-only admin sessions.
 */

export type AdminMetricsStreamHandlers = {
  onOpen?: () => void;
  onMessage: (payload: unknown) => void;
  onError?: () => void;
};

export function connectAdminMetricsStream(handlers: AdminMetricsStreamHandlers): () => void {
  if (typeof window === 'undefined') return () => {};

  let ws: WebSocket | null = null;
  let es: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;

  const scheduleRetry = () => {
    if (stopped) return;
    handlers.onError?.();
    retryTimer = setTimeout(connect, 5000);
  };

  const connect = () => {
    if (stopped) return;
    const token = localStorage.getItem('admin_token');
    if (token) {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${proto}//${window.location.host}/api/admin/ws/metrics`;
      ws = new WebSocket(url, ['Bearer', token]);
      ws.onopen = () => handlers.onOpen?.();
      ws.onmessage = (ev) => {
        try {
          handlers.onMessage(JSON.parse(ev.data));
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        ws?.close();
      };
      ws.onclose = (ev) => {
        ws = null;
        if (!stopped && !ev.wasClean) scheduleRetry();
      };
      return;
    }

    es = new EventSource('/api/admin/metrics/stream');
    es.onopen = () => handlers.onOpen?.();
    es.onmessage = (ev) => {
      try {
        handlers.onMessage(JSON.parse(ev.data));
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      es?.close();
      es = null;
      scheduleRetry();
    };
  };

  connect();

  return () => {
    stopped = true;
    clearTimeout(retryTimer);
    ws?.close();
    es?.close();
  };
}
