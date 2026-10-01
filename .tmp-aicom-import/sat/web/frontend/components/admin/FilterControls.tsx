'use client';

import React from 'react';

export function FilterResetSummary({
  onReset,
  summary,
  resetLabel = 'Reset filters',
  className = 'text-xs text-gray-500 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3 pr-1',
}: {
  onReset: () => void;
  summary: React.ReactNode;
  resetLabel?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <button
        type="button"
        onClick={onReset}
        className="shrink-0 text-left text-indigo-300 hover:text-indigo-200 underline underline-offset-2"
      >
        {resetLabel}
      </button>
      <span className="min-w-0 break-words text-gray-400 sm:text-right">{summary}</span>
    </div>
  );
}

export function FilterControlsPanel({
  children,
  onReset,
  summary,
  resetLabel = 'Reset filters',
  gridClassName = 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2',
}: {
  children: React.ReactNode;
  onReset: () => void;
  summary: React.ReactNode;
  resetLabel?: string;
  gridClassName?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className={gridClassName}>{children}</div>
      <FilterResetSummary onReset={onReset} resetLabel={resetLabel} summary={summary} />
    </div>
  );
}

const FILTER_CONTROL_CLASS =
  'bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50';

export function FilterSelect({
  className = '',
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${FILTER_CONTROL_CLASS} ${className}`.trim()} />;
}

export function FilterNumberInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} type="number" className={FILTER_CONTROL_CLASS} />;
}
