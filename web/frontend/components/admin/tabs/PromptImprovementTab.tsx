'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Sparkles, Wand2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { type AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

type Proposal = {
  id: string;
  agent_type: string;
  failure_count_7d?: number;
  hypothesis?: string;
  patch_preview?: string;
  status?: string;
  prompt_file?: string;
};

export function PromptImprovementTab({ locale }: { locale: AdminLocale }) {
  const [rows, setRows] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getPromptProposals();
      setRows(r.proposals || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const analyze = async () => {
    setAnalyzing(true);
    try {
      const r = await api.analyzePromptFailures();
      toast.success(`${r.count || 0} new proposals`);
      await load();
    } catch {
      toast.error('Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  const apply = async (id: string) => {
    setApplying(id);
    try {
      await api.applyPromptProposal(id);
      toast.success('Patch applied to prompt file');
      await load();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Apply failed');
    } finally {
      setApplying(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-400" />
            {t(locale, 'tab.promptLoop')}
          </h2>
          <p className="text-xs text-gray-500 mt-1">{t(locale, 'wow.promptLoopIntro')}</p>
        </div>
        <Button onClick={() => void analyze()} disabled={analyzing}>
          {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
          Analyze failures
        </Button>
      </div>

      {loading ? (
        <div className="flex h-32 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-indigo-400" /></div>
      ) : rows.length === 0 ? (
        <GlassCard className="p-6 text-sm text-gray-500">No proposals yet — run analysis on recent failed tasks.</GlassCard>
      ) : (
        <div className="space-y-3">
          {rows.map((p) => (
            <GlassCard key={p.id} className="p-4 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-white">{p.agent_type}</span>
                <span className="text-[10px] uppercase tracking-wide text-gray-500">{p.status}</span>
              </div>
              <p className="text-xs text-gray-400">{p.hypothesis}</p>
              {p.patch_preview ? (
                <pre className="text-[11px] text-indigo-200/80 bg-black/30 rounded p-2 whitespace-pre-wrap">{p.patch_preview}</pre>
              ) : null}
              {p.status === 'proposed' ? (
                <Button size="sm" onClick={() => void apply(p.id)} disabled={applying === p.id}>
                  {applying === p.id ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                  Apply A/B patch
                </Button>
              ) : null}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
