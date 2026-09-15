'use client';

import React from 'react';
import { AlertTriangle, Clock, Sparkles, Star } from 'lucide-react';

export type ProductPulseDot = 'done' | 'run' | 'todo' | 'fail';

export interface ProductPulsePayload {
  product_id: string;
  current_stage: string;
  current_agent_label: string;
  current_status: string;
  completed_stages: number;
  total_stages: number;
  stage_dots: ProductPulseDot[];
  eta_seconds?: number | null;
  eta_label?: string | null;
  tech_stack: string[];
  quality_pulse: 'green' | 'amber' | 'red' | 'unknown';
  quality_hint: string;
  quality_score?: number | null;
  health: 'ok' | 'stuck' | 'degraded';
  health_hint?: string | null;
  pipeline_state?: string;
}

const STAGE_ICONS: Record<string, string> = {
  analyst: '🔍',
  pm: '📋',
  marketing: '📢',
  methodologist: '🧭',
  architect: '🏗️',
  designer: '🎨',
  developer: '💻',
  qa: '🧪',
  security: '🛡️',
  devops: '🚀',
  sales: '💰',
};

function qualityEmoji(pulse: ProductPulsePayload['quality_pulse']) {
  if (pulse === 'green') return '🟢';
  if (pulse === 'amber') return '🟡';
  if (pulse === 'red') return '🔴';
  return '⚪';
}

export function ProductPulse({ pulse }: { pulse: ProductPulsePayload }) {
  const icon = STAGE_ICONS[pulse.current_stage] || '⚙️';
  const dots = pulse.stage_dots?.length ? pulse.stage_dots : [];

  return (
    <div
      className="mb-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-[11px] text-gray-300"
      aria-label="Product pulse — live pipeline snapshot"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1.5 font-medium text-gray-100">
          <span aria-hidden>{icon}</span>
          <span>{pulse.current_agent_label}</span>
          <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-200">
            {pulse.completed_stages}/{pulse.total_stages}
          </span>
        </span>
        {pulse.eta_label ? (
          <span className="inline-flex items-center gap-1 text-amber-200/90">
            <Clock className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
            {pulse.eta_label}
          </span>
        ) : null}
        {pulse.health === 'stuck' ? (
          <span
            className="inline-flex items-center gap-1 text-amber-300"
            title={pulse.health_hint || 'Stage running longer than expected'}
          >
            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
            Slow / stuck
          </span>
        ) : pulse.health === 'degraded' ? (
          <span className="inline-flex items-center gap-1 text-red-300/90" title={pulse.health_hint || ''}>
            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
            Issues
          </span>
        ) : null}
      </div>

      {pulse.tech_stack?.length ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="text-gray-500" aria-hidden>
            🛡️
          </span>
          {pulse.tech_stack.map((t) => (
            <span
              key={t}
              className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-gray-400"
            >
              {t}
            </span>
          ))}
        </div>
      ) : null}

      {dots.length > 0 ? (
        <div
          className="mt-2 flex items-center gap-0.5"
          role="img"
          aria-label={`Stages: ${pulse.completed_stages} of ${pulse.total_stages} completed`}
        >
          {dots.map((d, i) => (
            <span
              key={i}
              className={
                d === 'done'
                  ? 'h-2 w-2 rounded-full bg-emerald-500'
                  : d === 'run'
                    ? 'h-2 w-2 rounded-full bg-amber-400 animate-pulse'
                    : d === 'fail'
                      ? 'h-2 w-2 rounded-full bg-red-500'
                      : 'h-2 w-2 rounded-full bg-white/15'
              }
            />
          ))}
        </div>
      ) : null}

      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-gray-400">
        <span className="inline-flex items-center gap-1" title={pulse.quality_hint}>
          <Star className="h-3 w-3 text-amber-400/80" aria-hidden />
          <span aria-hidden>{qualityEmoji(pulse.quality_pulse)}</span>
          <span className="text-gray-400">
            Quality
            {typeof pulse.quality_score === 'number'
              ? `: ${pulse.quality_score.toFixed(1)}`
              : pulse.quality_pulse !== 'unknown'
                ? ` · ${pulse.quality_pulse}`
                : ''}
          </span>
        </span>
        {pulse.current_status === 'running' ? (
          <span className="inline-flex items-center gap-1 text-fuchsia-300/90">
            <Sparkles className="h-3 w-3" aria-hidden />
            Active
          </span>
        ) : null}
      </div>
    </div>
  );
}
