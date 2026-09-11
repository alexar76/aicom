'use client';

import Link from 'next/link';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import type { ResolvedFailure } from '@/lib/actionableErrors';
import { Button } from '@/components/ui/Button';

type Props = {
  failure: ResolvedFailure;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
};

export function ActionableFailurePanel({ failure, onRetry, retryLabel = 'Try again', className = '' }: Props) {
  return (
    <div
      role="alert"
      className={`rounded-xl border border-red-500/35 bg-red-950/25 p-4 text-sm ${className}`.trim()}
    >
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="font-medium text-red-100">{failure.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-red-100/80">{failure.detail}</p>
          </div>
          {(failure.actions.length > 0 || onRetry) && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {onRetry ? (
                <Button type="button" size="sm" variant="secondary" onClick={onRetry} icon={<RefreshCw className="h-3.5 w-3.5" />}>
                  {retryLabel}
                </Button>
              ) : null}
              {failure.actions.map((a) => (
                <Link
                  key={a.href}
                  href={a.href}
                  className="inline-flex items-center rounded-lg border border-red-400/35 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-50 hover:bg-red-500/20"
                >
                  {a.label}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
