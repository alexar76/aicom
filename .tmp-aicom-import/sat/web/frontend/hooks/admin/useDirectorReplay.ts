'use client';

import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '@/lib/api';

export function useDirectorReplay() {
  const [replayProductId, setReplayProductId] = useState('');
  const [replaySessions, setReplaySessions] = useState<any[]>([]);
  const [replaySessionId, setReplaySessionId] = useState('');
  const [replayTimeline, setReplayTimeline] = useState<any[]>([]);
  const [replayLoading, setReplayLoading] = useState(false);

  const loadReplaySessions = async () => {
    const pid = replayProductId.trim();
    if (!pid) return;
    setReplayLoading(true);
    try {
      const res = await api.getTelemetryReplaySessions(pid);
      setReplaySessions(res.sessions || []);
      setReplayTimeline([]);
      setReplaySessionId('');
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load replay sessions');
    } finally {
      setReplayLoading(false);
    }
  };

  const loadReplayTimeline = async (sid: string) => {
    const pid = replayProductId.trim();
    if (!pid || !sid) return;
    setReplayLoading(true);
    try {
      const res = await api.getTelemetryReplayTimeline(pid, sid);
      setReplaySessionId(sid);
      setReplayTimeline(res.events || []);
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load replay timeline');
    } finally {
      setReplayLoading(false);
    }
  };

  return {
    replayProductId,
    setReplayProductId,
    replaySessions,
    replaySessionId,
    replayTimeline,
    replayLoading,
    loadReplaySessions,
    loadReplayTimeline,
  };
}
