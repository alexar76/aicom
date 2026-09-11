'use client';

import React from 'react';
import { Loader2 } from 'lucide-react';
import { ProgressBar } from '@/components/ui/ProgressBar';
import type { SandboxLaunchProgress } from '@/lib/sandboxLaunch';
import {
  normalizeSandboxLaunchLocale,
  sandboxLaunchLabel,
  type SandboxLaunchLocale,
} from '@/lib/sandboxLaunchI18n';

export function SandboxLaunchOverlay({
  open,
  progress,
  locale = 'en',
}: {
  open: boolean;
  progress: SandboxLaunchProgress | null;
  locale?: SandboxLaunchLocale | string | null;
}) {
  if (!open) return null;
  const loc = normalizeSandboxLaunchLocale(locale);
  const pct = progress?.percent ?? 5;
  const label = progress?.label ?? sandboxLaunchLabel(loc, 'starting');
  const title = sandboxLaunchLabel(loc, 'title');

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="w-full max-w-md mx-4 rounded-2xl border border-white/10 bg-[#0f0f1a]/95 p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" aria-hidden />
          <div>
            <p className="text-white font-semibold">{title}</p>
            <p className="text-sm text-gray-400">{label}</p>
          </div>
        </div>
        <ProgressBar value={pct} max={100} className="h-2" showValue={false} />
        <p className="text-right text-xs text-indigo-300 mt-2 tabular-nums">{Math.round(pct)}%</p>
      </div>
    </div>
  );
}
