'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArrowUpRight, Github, Orbit } from 'lucide-react';
import type { MarketingStrings } from '@/lib/marketing';

type Props = {
  copy: Pick<
    MarketingStrings,
    | 'logosEyebrow'
    | 'logosTitle'
    | 'logosBody'
    | 'logosReadOnly'
    | 'logosDashboard'
    | 'logosSource'
    | 'logosDocs'
  >;
};

const SOURCES = [
  { name: 'AIMarket Hub', detail: 'federation', angle: -86 },
  { name: 'MOMUS', detail: 'findings', angle: 4 },
  { name: 'Treasury', detail: 'balance', angle: 94 },
  { name: 'SKOPOS', detail: 'remediation', angle: 184 },
] as const;

export function LogosEcosystemSection({ copy }: Props) {
  return (
    <section className="px-3 py-12 sm:px-4 sm:py-20" id="logos-analytics">
      <div className="mx-auto grid max-w-6xl items-center gap-10 overflow-hidden rounded-[2rem] border border-cyan-300/15 bg-[radial-gradient(circle_at_80%_30%,rgba(34,211,238,0.13),transparent_38%),radial-gradient(circle_at_20%_80%,rgba(129,140,248,0.12),transparent_42%),rgba(3,7,18,0.72)] p-6 shadow-[0_32px_100px_-48px_rgba(34,211,238,0.42)] ring-1 ring-white/5 backdrop-blur-xl md:grid-cols-[0.92fr_1.08fr] md:p-10 lg:p-14">
        <motion.div
          initial={{ opacity: 0, x: -18 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.45 }}
          className="relative z-10"
        >
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-300/90">{copy.logosEyebrow}</p>
          <h2 className="max-w-xl text-3xl font-bold tracking-tight text-white md:text-4xl">{copy.logosTitle}</h2>
          <p className="mt-4 max-w-xl text-base leading-7 text-gray-300/85">{copy.logosBody}</p>
          <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-300/5 px-3 py-1.5 text-xs font-medium text-emerald-200">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,0.9)]" />
            {copy.logosReadOnly}
          </div>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href="https://logos.modelmarket.dev/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200">
              {copy.logosDashboard}<ArrowUpRight className="h-4 w-4" aria-hidden />
            </a>
            <a href="https://github.com/alexar76/logos" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white transition hover:border-white/25 hover:bg-white/10">
              <Github className="h-4 w-4" aria-hidden />{copy.logosSource}
            </a>
            <a href="https://github.com/alexar76/logos#readme" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 px-2 py-2.5 text-sm font-medium text-cyan-200 transition hover:text-cyan-100">
              {copy.logosDocs}<ArrowUpRight className="h-4 w-4" aria-hidden />
            </a>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55 }}
          className="relative mx-auto aspect-square w-full max-w-[30rem]"
          aria-label="LOGOS read-only federation data topology"
        >
          <div className="absolute inset-[15%] rounded-full bg-cyan-300/10 blur-3xl" aria-hidden />
          <div className="absolute inset-[8%] animate-[spin_34s_linear_infinite] rounded-full border border-dashed border-cyan-200/20" aria-hidden />
          <div className="absolute inset-[22%] animate-[spin_22s_linear_infinite_reverse] rounded-full border border-indigo-300/20" aria-hidden />
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 400" aria-hidden>
            <defs>
              <linearGradient id="logos-link" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#67e8f9" stopOpacity="0.55" />
                <stop offset="1" stopColor="#818cf8" stopOpacity="0.14" />
              </linearGradient>
            </defs>
            {SOURCES.map(({ angle, name }) => {
              const rad = (angle * Math.PI) / 180;
              return <line key={name} x1="200" y1="200" x2={200 + Math.cos(rad) * 148} y2={200 + Math.sin(rad) * 148} stroke="url(#logos-link)" strokeWidth="1.2" strokeDasharray="3 5" />;
            })}
          </svg>
          <div className="absolute left-1/2 top-1/2 flex h-[8.5rem] w-[8.5rem] -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border border-cyan-100/25 bg-[radial-gradient(circle_at_35%_25%,rgba(207,250,254,0.34),rgba(8,145,178,0.18)_28%,rgba(15,23,42,0.96)_68%)] shadow-[0_0_72px_rgba(34,211,238,0.28),inset_0_0_30px_rgba(103,232,249,0.13)] ring-1 ring-cyan-200/10">
            <Orbit className="mb-1 h-7 w-7 text-cyan-200" aria-hidden />
            <span className="text-lg font-bold tracking-[0.18em] text-white">LOGOS</span>
            <span className="mt-1 text-[9px] uppercase tracking-[0.2em] text-cyan-200/70">read-only</span>
          </div>
          {SOURCES.map(({ name, detail, angle }, index) => {
            const rad = (angle * Math.PI) / 180;
            return (
              <motion.div key={name} initial={{ opacity: 0, scale: 0.8 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.12 + index * 0.08 }} className="absolute w-[7.5rem] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-slate-950/75 px-2.5 py-2 text-center shadow-xl backdrop-blur-md" style={{ left: `${50 + Math.cos(rad) * 37}%`, top: `${50 + Math.sin(rad) * 37}%` }}>
                <p className="text-[11px] font-semibold text-white">{name}</p>
                <p className="mt-0.5 text-[9px] uppercase tracking-wider text-cyan-200/55">{detail}</p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
