'use client';

import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import { AdminLocale, t, tVars } from '@/lib/adminI18n';

export function useDirectorData(locale: AdminLocale) {
  const [reports, setReports] = useState<any[]>([]);
  const [analysisData, setAnalysisData] = useState<any>(null);
  const [benchmarkData, setBenchmarkData] = useState<{
    scorecard?: any;
    alerts?: any[];
    status?: any;
    investor_metrics?: any;
  } | null>(null);
  const [expandedReport, setExpandedReport] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<{
    pending: any[];
    applied: any[];
    pending_count: number;
    total_count: number;
  }>({ pending: [], applied: [], pending_count: 0, total_count: 0 });
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [benchmarkTriggering, setBenchmarkTriggering] = useState(false);
  const [renamingCatalog, setRenamingCatalog] = useState(false);
  const [remediatingCatalog, setRemediatingCatalog] = useState(false);
  const [feedbackSummary, setFeedbackSummary] = useState<any>(null);
  const [discoveryQueue, setDiscoveryQueue] = useState<any[]>([]);
  const [discoveryMeta, setDiscoveryMeta] = useState<any>(null);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [directorQuery, setDirectorQuery] = useState('');
  const [directorCategoryFilter, setDirectorCategoryFilter] = useState('all');
  const [directorMinScore, setDirectorMinScore] = useState('');

  useEffect(() => {
    api.getDirectorReports().then(setReports).catch(() => {});
    api.getDirectorAnalysis().then(setAnalysisData).catch(() => {});
    api.getDirectorDecisions().then(setDecisions).catch(() => {});
    api.getBenchmarkScorecard().then(setBenchmarkData).catch(() => {});
    api.getAdminFeedbackSummary(168).then(setFeedbackSummary).catch(() => {});
    api.getDiscoveryIdeas(20).then((x) => {
      setDiscoveryQueue(x.ranked_ideas || []);
      setDiscoveryMeta(x);
    }).catch(() => {});
  }, []);

  const handleApprove = async (decisionId: string) => {
    setActionInProgress(decisionId);
    try {
      await api.approveDecision(decisionId);
      setDecisions(await api.getDirectorDecisions());
    } catch {
      /* ignore */
    }
    setActionInProgress(null);
  };

  const handleReject = async (decisionId: string) => {
    setActionInProgress(decisionId);
    try {
      await api.rejectDecision(decisionId);
      setDecisions(await api.getDirectorDecisions());
    } catch {
      /* ignore */
    }
    setActionInProgress(null);
  };

  const handleTriggerBenchmark = async () => {
    setBenchmarkTriggering(true);
    try {
      await api.triggerBenchmarkLeague();
      setBenchmarkData(await api.getBenchmarkScorecard());
      toast.success('Benchmark league triggered');
    } catch (e: any) {
      toast.error(e?.message || 'Failed to trigger benchmark');
    } finally {
      setBenchmarkTriggering(false);
    }
  };

  const handleRenameCatalogProducts = async () => {
    setRenamingCatalog(true);
    try {
      const res = await api.renameCatalogProductsNow();
      toast.success(`Renamed ${res.renamed_count} products`);
    } catch (e: any) {
      toast.error(e?.message || 'Failed to rename catalog products');
    } finally {
      setRenamingCatalog(false);
    }
  };

  const handleRemediateCatalogCompliance = async () => {
    setRemediatingCatalog(true);
    try {
      const res = await api.remediateCatalogComplianceNow();
      toast.success(`Compliance sweep done: processed ${res.processed}, rerouted ${res.rerouted}`);
    } catch (e: any) {
      toast.error(e?.message || 'Failed to run compliance remediation');
    } finally {
      setRemediatingCatalog(false);
    }
  };

  const refreshDiscovery = async (createProduct: boolean) => {
    setDiscoveryLoading(true);
    try {
      const run = await api.runDiscovery(createProduct, 12);
      const x = await api.getDiscoveryIdeas(20);
      setDiscoveryQueue(x.ranked_ideas || []);
      setDiscoveryMeta(x);
      if (createProduct && run?.created_product_id) {
        toast.success(tVars(locale, 'discovery.toastQueuedWithId', { id: run.created_product_id }));
      } else {
        toast.success(t(locale, 'discovery.toastRefreshed'));
      }
    } catch (e: any) {
      toast.error(e?.message || 'Failed to refresh discovery');
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const directorDiscoveryCategories = useMemo(
    () =>
      Array.from(
        new Set(discoveryQueue.map((idea: any) => String(idea?.category || '')).filter(Boolean)),
      ).sort(),
    [discoveryQueue],
  );

  const filteredDirectorDiscoveryQueue = useMemo(() => {
    const q = directorQuery.trim().toLowerCase();
    const min = directorMinScore.trim() === '' ? null : Number(directorMinScore);
    return discoveryQueue.filter((idea: any) => {
      const category = String(idea?.category || '');
      if (directorCategoryFilter !== 'all' && category !== directorCategoryFilter) return false;
      const scoreNum = Number(idea?.balanced_score ?? idea?.score_total ?? 0);
      if (min != null && Number.isFinite(min) && scoreNum < min) return false;
      if (!q) return true;
      const text = String(idea?.idea || '').toLowerCase();
      return text.includes(q) || category.toLowerCase().includes(q);
    });
  }, [discoveryQueue, directorQuery, directorCategoryFilter, directorMinScore]);

  const filteredPendingDecisions = useMemo(() => {
    const q = directorQuery.trim().toLowerCase();
    if (!q) return decisions.pending;
    return decisions.pending.filter((d: any) => {
      const action = String(d?.action || '').toLowerCase();
      const target = String(d?.target || '').toLowerCase();
      const reason = String(d?.reason || '').toLowerCase();
      return action.includes(q) || target.includes(q) || reason.includes(q);
    });
  }, [decisions.pending, directorQuery]);

  const filteredReports = useMemo(() => {
    const q = directorQuery.trim().toLowerCase();
    if (!q) return reports;
    return reports.filter((r: any) => {
      const fn = String(r?.filename || '').toLowerCase();
      const date = String(r?.date || '').toLowerCase();
      return fn.includes(q) || date.includes(q);
    });
  }, [reports, directorQuery]);

  const formatDecisionTime = (ts: number | null | undefined) => {
    if (!ts) return '—';
    const secs = Math.floor((Date.now() - ts * 1000) / 1000);
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
  };

  const getActionLabel = (action: string) =>
    action.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase());

  return {
    reports,
    analysisData,
    benchmarkData,
    expandedReport,
    setExpandedReport,
    decisions,
    actionInProgress,
    benchmarkTriggering,
    renamingCatalog,
    remediatingCatalog,
    feedbackSummary,
    discoveryQueue,
    discoveryMeta,
    discoveryLoading,
    directorQuery,
    setDirectorQuery,
    directorCategoryFilter,
    setDirectorCategoryFilter,
    directorMinScore,
    setDirectorMinScore,
    handleApprove,
    handleReject,
    handleTriggerBenchmark,
    handleRenameCatalogProducts,
    handleRemediateCatalogCompliance,
    refreshDiscovery,
    directorDiscoveryCategories,
    filteredDirectorDiscoveryQueue,
    filteredPendingDecisions,
    filteredReports,
    formatDecisionTime,
    getActionLabel,
  };
}
