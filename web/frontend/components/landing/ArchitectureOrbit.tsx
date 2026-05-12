'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
  Bot,
  Brain,
  Cpu,
  Database,
  Globe,
  LayoutDashboard,
  Server,
  Workflow,
} from 'lucide-react';

const CX = 200;
const CY = 200;
const R_ORBIT = 158;
const R_LINE = 148;

function polar(deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + R_ORBIT * Math.cos(rad), y: CY + R_ORBIT * Math.sin(rad) };
}

function lineEnd(deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + R_LINE * Math.cos(rad), y: CY + R_LINE * Math.sin(rad) };
}

const NODES: {
  deg: number;
  label: string;
  sub: string;
  Icon: React.ComponentType<{ className?: string }>;
}[] = [
  { deg: -90, label: 'Next.js', sub: 'Storefront', Icon: Globe },
  { deg: -18, label: 'FastAPI', sub: 'Public & admin API', Icon: Server },
  { deg: 54, label: 'Pipeline worker', sub: 'Quality gates', Icon: Workflow },
  { deg: 126, label: 'Director AI', sub: 'Signals & reports', Icon: LayoutDashboard },
  { deg: 198, label: 'LLM router', sub: 'Multi-provider', Icon: Brain },
  { deg: 270, label: 'Data plane', sub: 'SQLite · artifacts', Icon: Database },
];

export function ArchitectureOrbit() {
  return (
    <section className="py-12 sm:py-20 px-3 sm:px-4" id="architecture">
      <div className="max-w-6xl mx-auto min-w-0">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-300/90 mb-2">
            Runtime topology
          </p>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-3">Architecture at a glance</h2>
          <p className="text-gray-400 text-base max-w-xl mx-auto">
            One control plane: web tier, background workers, routed models, and durable workspace — shown as a live orbit around the agent fleet.
          </p>
        </motion.div>

        {/* Centered in the column, then shifted 50px left vs geometric center (visual balance). */}
        <div className="flex w-full min-w-0 justify-center overflow-x-clip">
          <div className="relative w-full max-w-[min(100vw-2rem,480px)] aspect-square min-h-0 -translate-x-[50px]">
          {/* Soft glow */}
          <div
            className="pointer-events-none absolute inset-[10%] rounded-full opacity-50 blur-3xl bg-[conic-gradient(from_180deg_at_50%_50%,rgba(99,102,241,0.35),rgba(168,85,247,0.25),rgba(34,211,238,0.3),rgba(99,102,241,0.35))]"
            aria-hidden
          />

          <svg
            className="absolute inset-0 h-full w-full text-white/10"
            viewBox="0 0 400 400"
            aria-hidden
          >
            <defs>
              <linearGradient id="arch-orbit-stroke" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="45%" stopColor="#c084fc" />
                <stop offset="100%" stopColor="#22d3ee" />
              </linearGradient>
            </defs>

            <circle
              cx={CX}
              cy={CY}
              r={R_ORBIT}
              fill="none"
              stroke="url(#arch-orbit-stroke)"
              strokeWidth={2}
              strokeDasharray="10 16"
              opacity={0.55}
            >
              <animateTransform
                attributeName="transform"
                type="rotate"
                from={`0 ${CX} ${CY}`}
                to={`360 ${CX} ${CY}`}
                dur="96s"
                repeatCount="indefinite"
              />
            </circle>

            {NODES.map(({ deg }) => {
              const { x: x2, y: y2 } = lineEnd(deg);
              return (
                <line
                  key={`ln-${deg}`}
                  x1={CX}
                  y1={CY}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeOpacity={0.22}
                  strokeWidth={1}
                />
              );
            })}
          </svg>

          {/* Center hub */}
          <div className="absolute left-1/2 top-1/2 z-10 w-[min(42%,200px)] -translate-x-1/2 -translate-y-1/2">
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }}
              whileInView={{ scale: 1, opacity: 1 }}
              viewport={{ once: true }}
              transition={{ type: 'spring', stiffness: 260, damping: 22 }}
              className="rounded-full border border-white/15 bg-gradient-to-br from-indigo-600/40 via-purple-600/30 to-cyan-600/25 p-6 text-center shadow-[0_0_60px_-12px_rgba(99,102,241,0.55)] backdrop-blur-md ring-1 ring-white/10"
            >
              <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-black/30 ring-1 ring-white/10">
                <Bot className="h-7 w-7 text-indigo-200" aria-hidden />
              </div>
              <p className="text-xs font-semibold uppercase tracking-wider text-indigo-200/90">Agents</p>
              <p className="mt-1 text-[11px] leading-snug text-gray-300/90">
                PM · Architect · Dev · QA · Sec · Ops · Mkt · Sales · Evolution
              </p>
              <div className="mt-3 flex items-center justify-center gap-1 text-[10px] text-cyan-200/80">
                <Cpu className="h-3 w-3" />
                <span>Single pipeline · shared gates</span>
              </div>
            </motion.div>
          </div>

          {/* Satellites */}
          {NODES.map(({ deg, label, sub, Icon }, i) => {
            const { x, y } = polar(deg);
            const left = (x / 400) * 100;
            const top = (y / 400) * 100;
            return (
              <motion.div
                key={deg}
                initial={{ opacity: 0, scale: 0.85 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: 0.06 * i, duration: 0.35 }}
                className="absolute z-20 w-[30%] max-w-[9.5rem] min-w-[7rem]"
                style={{
                  left: `${left}%`,
                  top: `${top}%`,
                  transform: 'translate(-50%, -50%)',
                }}
              >
                <div className="rounded-2xl border border-white/12 bg-black/55 px-3 py-2.5 text-center shadow-lg backdrop-blur-md ring-1 ring-white/5">
                  <Icon className="mx-auto mb-1 h-5 w-5 text-cyan-300/90" aria-hidden />
                  <p className="text-[11px] font-semibold leading-tight text-white">{label}</p>
                  <p className="mt-0.5 text-[10px] leading-snug text-gray-500">{sub}</p>
                </div>
              </motion.div>
            );
          })}
          </div>
        </div>
      </div>
    </section>
  );
}
