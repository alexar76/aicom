'use client';

import { motion } from 'framer-motion';
import { Brain, Cpu } from 'lucide-react';
import type { FactoryIqStrings } from '@/lib/marketing-iq';

const NODE_DEG = [-90, -18, 54, 126, 198, 270] as const;
const CX = 200;
const CY = 200;
const R = 148;

function polar(deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + R * Math.cos(rad), y: CY + R * Math.sin(rad) };
}

type Props = {
  copy: FactoryIqStrings;
  iq: number | null;
  modelCount: number;
};

export function FactoryIqBrainScene({ copy, iq, modelCount }: Props) {
  const nodes = copy.swarmNodes.map((n, i) => ({ ...n, deg: NODE_DEG[i] }));

  return (
    <div className="relative w-full max-w-lg mx-auto aspect-square">
      <div
        className="absolute inset-[8%] rounded-full opacity-60 blur-3xl bg-[conic-gradient(from_120deg_at_50%_50%,rgba(34,211,238,0.45),rgba(139,92,246,0.35),rgba(99,102,241,0.4),rgba(34,211,238,0.45))]"
        aria-hidden
      />

      {/* 3D brain core */}
      <div className="absolute inset-0 flex items-center justify-center perspective-[900px]">
        <motion.div
          animate={{ rotateY: [0, 8, 0, -8, 0], rotateX: [0, -6, 0, 6, 0] }}
          transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut' }}
          className="relative w-40 h-40 sm:w-48 sm:h-48"
          style={{ transformStyle: 'preserve-3d' }}
        >
          <div className="absolute inset-0 rounded-[42%] bg-gradient-to-br from-cyan-400/30 via-violet-500/25 to-indigo-600/30 border border-cyan-300/30 shadow-[0_0_60px_rgba(34,211,238,0.35)] backdrop-blur-sm" />
          <div className="absolute inset-2 rounded-[40%] bg-gradient-to-tr from-violet-600/20 to-transparent border border-white/10" />
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
            <Brain className="w-14 h-14 sm:w-16 sm:h-16 text-cyan-200 drop-shadow-[0_0_12px_rgba(34,211,238,0.8)]" />
            <span className="text-3xl sm:text-4xl font-black bg-gradient-to-r from-cyan-200 to-violet-300 bg-clip-text text-transparent tabular-nums">
              {iq == null ? '—' : iq.toFixed(1)}
            </span>
            <span className="text-[10px] uppercase tracking-widest text-cyan-200/70">{copy.heroIqLabel}</span>
          </div>
        </motion.div>
      </div>

      <svg viewBox="0 0 400 400" className="absolute inset-0 w-full h-full text-white/10 pointer-events-none">
        {nodes.map((n) => {
          const p = polar(n.deg);
          return (
            <line key={n.role} x1={CX} y1={CY} x2={p.x} y2={p.y} stroke="currentColor" strokeDasharray="4 6" />
          );
        })}
      </svg>

      {nodes.map((n, i) => {
        const p = polar(n.deg);
        const left = `${(p.x / 400) * 100}%`;
        const top = `${(p.y / 400) * 100}%`;
        return (
          <motion.div
            key={n.role}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left, top }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.08 }}
          >
            <div className="rounded-xl border border-white/15 bg-black/70 backdrop-blur-md px-2.5 py-1.5 text-center shadow-lg shadow-cyan-500/10 min-w-[5.5rem]">
              <div className="text-[11px] font-bold text-cyan-200">{n.role}</div>
              <div className="text-[9px] text-gray-400 leading-tight">{n.task}</div>
            </div>
          </motion.div>
        );
      })}

      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full border border-white/10 bg-black/50 px-3 py-1 text-[10px] text-gray-400">
        <Cpu className="w-3 h-3 text-violet-300" />
        <span>
          {copy.modelsEvaluated}: <span className="text-white font-semibold">{modelCount}</span>
        </span>
      </div>
    </div>
  );
}
