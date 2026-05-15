'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { BookOpen, Sparkles, Wrench, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';

const STORAGE_KEY = 'aicom_admin_shell_onboarding_dismissed_v1';

type Props = {
  activeTab: string;
};

export function AdminShellOnboarding({ activeTab }: Props) {
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(STORAGE_KEY) === '1');
    } catch {
      setDismissed(false);
    }
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
    <GlassCard className="mb-6 border border-indigo-500/30 bg-indigo-950/30 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3">
          <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" aria-hidden />
          <div className="min-w-0 space-y-2">
            <h3 className="text-sm font-semibold text-indigo-50">Get oriented in three moves</h3>
            <ol className="list-decimal space-y-1.5 pl-4 text-xs leading-relaxed text-indigo-100/90">
              <li>
                <span className="font-medium text-white">See health first</span> — open{' '}
                <Link href="/admin?tab=dashboard" className="text-indigo-200 underline-offset-2 hover:underline">
                  Dashboard
                </Link>{' '}
                for queue depth and alerts.
              </li>
              <li>
                <span className="font-medium text-white">Queue real work</span> —{' '}
                <Link href="/admin?tab=new-product" className="text-indigo-200 underline-offset-2 hover:underline">
                  New product
                </Link>{' '}
                walks idea → options → review; save presets as local or cloud templates.
              </li>
              <li>
                <span className="font-medium text-white">Wire models once</span> —{' '}
                <Link href="/admin?tab=providers" className="text-indigo-200 underline-offset-2 hover:underline">
                  Providers
                </Link>{' '}
                and{' '}
                <Link href="/admin?tab=settings" className="text-indigo-200 underline-offset-2 hover:underline">
                  Settings
                </Link>{' '}
                so agents do not fail silently.
              </li>
            </ol>
            <p className="text-[11px] text-indigo-200/70">
              When something fails, look for retry plus links to Providers or Pipeline on the error card.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 lg:flex-col lg:items-end">
          <Link
            href="/admin?tab=new-product"
            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-400/40 bg-indigo-500/20 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500/30"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Start wizard
          </Link>
          <Link
            href="/admin?tab=workshop"
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-indigo-100 hover:bg-white/5"
          >
            <Wrench className="h-3.5 w-3.5" aria-hidden />
            Workshop tools
          </Link>
          <button
            type="button"
            className="rounded-lg p-1.5 text-indigo-200/80 hover:bg-white/10 hover:text-white"
            aria-label="Dismiss onboarding"
            onClick={dismiss}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      {activeTab === 'new-product' ? (
        <p className="mt-3 border-t border-white/10 pt-3 text-[11px] text-indigo-100/75">
          You are on <span className="text-white">New product</span>: use the left guide column for what each step
          expects, then apply a quick-start chip if you want a filled example idea.
        </p>
      ) : null}
    </GlassCard>
  );
}
