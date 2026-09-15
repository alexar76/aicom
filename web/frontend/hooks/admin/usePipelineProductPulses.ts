'use client';

import { useEffect, type Dispatch, type SetStateAction } from 'react';

/** Merge ``product_pulses`` from admin metrics SSE into pipeline product rows. */
export function usePipelineProductPulses(setProducts: Dispatch<SetStateAction<any[]>>) {
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource('/api/admin/metrics/stream');
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const pulses = data?.product_pulses;
          if (!pulses || typeof pulses !== 'object') return;
          setProducts((prev) =>
            prev.map((p) => {
              const pulse = pulses[p.id];
              return pulse ? { ...p, pulse } : p;
            }),
          );
        } catch {
          /* ignore */
        }
      };
    } catch {
      /* ignore */
    }
    return () => {
      es?.close();
    };
  }, [setProducts]);
}
