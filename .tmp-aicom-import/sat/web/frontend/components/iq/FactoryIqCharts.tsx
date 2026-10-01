'use client';

import { motion } from 'framer-motion';
import { GlassCard } from '@/components/ui/GlassCard';
import type { FactoryIqStrings } from '@/lib/marketing-iq';

export function EvAreaChart({
  values,
  emptyLabel,
  height = 120,
}: {
  values: number[];
  emptyLabel: string;
  height?: number;
}) {
  if (!values.length) {
    return (
      <div className="flex items-center justify-center text-gray-500 text-sm" style={{ height }}>
        {emptyLabel}
      </div>
    );
  }
  const w = 400;
  const h = height;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 8) - 4;
    return { x, y, v };
  });
  const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const area = `M0,${h} L${line} L${w},${h} Z`;
  const zeroY = h - ((0 - min) / span) * (h - 8) - 4;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }}>
      <defs>
        <linearGradient id="evFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(34,211,238)" stopOpacity="0.45" />
          <stop offset="100%" stopColor="rgb(139,92,246)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <line x1="0" y1={zeroY} x2={w} y2={zeroY} stroke="#475569" strokeDasharray="4 4" strokeWidth="1" />
      <path d={area} fill="url(#evFill)" />
      <polyline points={line} fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinejoin="round" />
      {pts.map((p, i) =>
        i % Math.max(1, Math.floor(pts.length / 8)) === 0 || i === pts.length - 1 ? (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#a5f3fc" opacity="0.9" />
        ) : null,
      )}
    </svg>
  );
}

export function IqGaugeRing({ iq, label }: { iq: number | null; label: string }) {
  const pct = iq == null ? 0 : Math.min(100, Math.max(0, iq)) / 100;
  const r = 52;
  const c = 2 * Math.PI * r;
  const dash = c * pct;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 120" className="w-28 h-28">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
        <motion.circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="url(#iqGrad)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          transform="rotate(-90 60 60)"
          initial={{ strokeDasharray: `0 ${c}` }}
          animate={{ strokeDasharray: `${dash} ${c}` }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        />
        <defs>
          <linearGradient id="iqGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <text x="60" y="58" textAnchor="middle" className="fill-white text-xl font-bold" fontSize="22">
          {iq == null ? '—' : iq.toFixed(1)}
        </text>
        <text x="60" y="74" textAnchor="middle" className="fill-gray-400" fontSize="8">
          {label}
        </text>
      </svg>
    </div>
  );
}

export function CompareBars({
  copy,
  liveMean,
  frozenMean,
}: {
  copy: FactoryIqStrings;
  liveMean: number;
  frozenMean: number | null;
}) {
  const max = Math.max(Math.abs(liveMean), Math.abs(frozenMean ?? 0), 0.01);
  const liveW = (Math.abs(liveMean) / max) * 100;
  const frozenW = frozenMean != null ? (Math.abs(frozenMean) / max) * 100 : 0;

  return (
    <div className="space-y-3">
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{copy.chartLive}</span>
          <span className="text-cyan-300 tabular-nums">{liveMean.toFixed(2)}</span>
        </div>
        <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-cyan-300"
            initial={{ width: 0 }}
            animate={{ width: `${liveW}%` }}
            transition={{ duration: 0.8 }}
          />
        </div>
      </div>
      {frozenMean != null && (
        <div>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{copy.chartControl}</span>
            <span className="text-violet-300 tabular-nums">{frozenMean.toFixed(2)}</span>
          </div>
          <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-violet-600 to-violet-400"
              initial={{ width: 0 }}
              animate={{ width: `${frozenW}%` }}
              transition={{ duration: 0.8, delay: 0.15 }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function CalibrationMeter({
  copy,
  error,
  samples,
}: {
  copy: FactoryIqStrings;
  error: number;
  samples: number;
}) {
  const trust = samples > 0 ? Math.max(0, Math.min(100, (1 - error) * 100)) : 0;
  return (
    <GlassCard hover={false} className="p-4">
      <div className="text-xs uppercase tracking-wide text-gray-400 mb-1">{copy.gatekeeper}</div>
      <div className="text-sm text-gray-500 mb-3">{copy.gatekeeperHint}</div>
      <div className="relative h-3 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-emerald-500 via-cyan-400 to-violet-400"
          initial={{ width: 0 }}
          animate={{ width: `${trust}%` }}
          transition={{ duration: 1 }}
        />
      </div>
      <div className="mt-2 flex justify-between text-xs text-gray-400">
        <span>n={samples}</span>
        <span className="text-gray-300">ε={error.toFixed(3)}</span>
      </div>
    </GlassCard>
  );
}
