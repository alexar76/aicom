'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Compass, Play, Rocket, Sparkles, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { isSetupWizardMarkedDone } from '@/components/admin/tabs/SetupWizardTab';

const STORAGE_KEY = 'aicom_pipeline_coach_dismissed_v1';

export function PipelineOnboardingCoach() {
  const [dismissed, setDismissed] = useState(true);
  const [setupDone, setSetupDone] = useState(false);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(STORAGE_KEY) === '1');
    } catch {
      setDismissed(false);
    }
    setSetupDone(isSetupWizardMarkedDone());
  }, []);

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore */
    }
    setDismissed(true);
  }, []);

  if (dismissed) return null;

  return (
    <GlassCard className="p-4 border border-violet-500/25 bg-violet-950/25">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3">
          <Compass className="mt-0.5 h-5 w-5 shrink-0 text-violet-300" aria-hidden />
          <div className="min-w-0 space-y-2">
            <h3 className="text-sm font-semibold text-violet-50">Pipeline in 60 seconds — no manual required</h3>
            {!setupDone ? (
              <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-amber-100/90">
                <Rocket className="mr-1 inline h-3.5 w-3.5 -mt-0.5" aria-hidden />
                Step 0: open{' '}
                <Link href="/admin?tab=setup" className="font-medium text-white underline-offset-2 hover:underline">
                  Setup wizard
                </Link>{' '}
                and save one LLM provider — otherwise every agent task will fail.
              </p>
            ) : null}
            <ol className="list-decimal space-y-1.5 pl-4 text-xs leading-relaxed text-violet-100/90">
              <li>
                <span className="font-medium text-white">Green row</span> = shipped (
                <code className="text-[10px]">COMPLETED</code>). Amber = fixing. Red = failed — expand for the
                error line.
              </li>
              <li>
                <span className="font-medium text-white">Muted rows</span> = cached snapshot; the bar under the title
                shows live hydration. Wait for 100% before trusting storefront counts.
              </li>
              <li>
                <span className="font-medium text-white">Queue work</span> —{' '}
                <Link href="/admin?tab=new-product" className="text-violet-200 underline-offset-2 hover:underline">
                  New product
                </Link>{' '}
                (idea → review → start). Turn on auto-pipeline in Settings if you want a steady stream.
              </li>
              <li>
                <span className="font-medium text-white">Stuck?</span> Check{' '}
                <Link href="/admin?tab=llm-logs" className="text-violet-200 underline-offset-2 hover:underline">
                  LLM Logs
                </Link>{' '}
                and filter State = <code className="text-[10px]">FAILED</code> here.
              </li>
            </ol>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 lg:flex-col lg:items-end">
          {!setupDone ? (
            <Link
              href="/admin?tab=setup"
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500/25"
            >
              <Rocket className="h-3.5 w-3.5" aria-hidden />
              Setup wizard
            </Link>
          ) : null}
          <Link
            href="/admin?tab=new-product"
            className="inline-flex items-center gap-1.5 rounded-lg border border-violet-400/40 bg-violet-500/20 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500/30"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            New product
          </Link>
          <Link
            href="/docs"
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-violet-100 hover:bg-white/5"
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            Optional deep dive
          </Link>
          <button
            type="button"
            className="rounded-lg p-1.5 text-violet-200/80 hover:bg-white/10 hover:text-white"
            aria-label="Dismiss pipeline coach"
            onClick={dismiss}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </GlassCard>
  );
}
