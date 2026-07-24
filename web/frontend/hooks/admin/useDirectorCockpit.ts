'use client';

import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '@/lib/api';

export function useDirectorCockpit() {
  const [cockpitProductId, setCockpitProductId] = useState('');
  const [cockpit, setCockpit] = useState<any>(null);
  const [cockpitLoading, setCockpitLoading] = useState(false);

  const loadCockpit = async () => {
    const pid = cockpitProductId.trim();
    if (!pid) return;
    setCockpitLoading(true);
    try {
      setCockpit(await api.getReleaseCockpit(pid));
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load release cockpit');
    } finally {
      setCockpitLoading(false);
    }
  };

  const executeProtocol = async () => {
    const pid = cockpitProductId.trim();
    if (!pid) return;
    setCockpitLoading(true);
    try {
      await api.executeReleaseProtocol(pid);
      setCockpit(await api.getReleaseCockpit(pid));
      toast.success('Release protocol executed');
    } catch (e: any) {
      toast.error(e?.message || 'Failed to execute protocol');
    } finally {
      setCockpitLoading(false);
    }
  };

  return {
    cockpitProductId,
    setCockpitProductId,
    cockpit,
    cockpitLoading,
    loadCockpit,
    executeProtocol,
  };
}
