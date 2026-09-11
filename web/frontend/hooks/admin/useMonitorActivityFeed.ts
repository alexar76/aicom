'use client';

import { useEffect, useState } from 'react';
import api from '@/lib/api';

export function useMonitorActivityFeed() {
  const [activityFeed, setActivityFeed] = useState<any[]>([]);
  const [escEventFilter, setEscEventFilter] = useState<string>('all');

  useEffect(() => {
    api.getEscalations(10).then((res) => {
      if (res.escalations?.length) {
        setActivityFeed(
          res.escalations.map((e: any) => ({
            type: 'escalation',
            agent: e.agent_type || 'system',
            message: e.error || e.action_taken || 'Escalation triggered',
            time: e.timestamp || Date.now(),
            severity: 'error',
          })),
        );
      }
    }).catch(() => {});

    api.getAgentLogs(undefined, 20).then((res) => {
      if (res.logs?.length) {
        setActivityFeed((prev) => {
          const logEntries = res.logs.map((l: any) => ({
            type: 'agent_log',
            agent: l.agent || l.agent_type || 'unknown',
            message: l.message || l.content || '—',
            time: l.timestamp || l.time || Date.now(),
            severity: l.level || 'info',
          }));
          return [...logEntries, ...prev].slice(0, 100);
        });
      }
    }).catch(() => {});
  }, []);

  return {
    activityFeed,
    escEventFilter,
    setEscEventFilter,
  };
}
