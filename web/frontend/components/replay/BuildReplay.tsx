'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Loader2,
  ShieldCheck,
  RefreshCw,
  Clock,
  Rocket,
  Github,
  ArrowRight,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import type { BuildReplay, BuildStage } from '@/lib/server-api';

const GITHUB_URL =
  process.env.NEXT_PUBLIC_GITHUB_URL || 'https://github.com/alexar76/aicom';
const STEP_MS = 1100; // auto-advance cadence per stage

function fmtDuration(sec: number | null | undefined): string {
  if (!sec || sec <= 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
}

function StatusIcon({ stage, active }: { stage: BuildStage; active: boolean }) {
  if (active && stage.status !== 'completed' && stage.status !== 'failed') {
    return <Loader2 className="w-5 h-5 text-cyan-300 animate-spin" />;
  }
  if (stage.status === 'failed' || stage.had_error) {
    return <XCircle className="w-5 h-5 text-rose-400" />;
  }
  if (stage.status === 'completed') {
    return <CheckCircle2 className="w-5 h-5 text-emerald-400" />;
  }
  return <Clock className="w-5 h-5 text-gray-500" />;
}

function HighlightChips({ highlights }: { highlights: BuildStage['highlights'] }) {
  const entries = Object.entries(highlights || {});
  if (!entries.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="text-[11px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-gray-300"
        >
          <span className="text-gray-500">{k}:</span>{' '}
          {typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v)}
        </span>
      ))}
    </div>
  );
}

export function BuildReplayView({ replay }: { replay: BuildReplay }) {
  const { build, stages } = replay;
  const total = stages.length;
  const [cursor, setCursor] = useState(total ? total - 1 : 0); // start fully revealed
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => () => clearTimer(), [clearTimer]);

  useEffect(() => {
    if (!playing) {
      clearTimer();
      return;
    }
    timer.current = setInterval(() => {
      setCursor((c) => {
        if (c >= total - 1) {
          setPlaying(false);
          return c;
        }
        return c + 1;
      });
    }, STEP_MS);
    return clearTimer;
  }, [playing, total, clearTimer]);

  const play = useCallback(() => {
    if (cursor >= total - 1) setCursor(0);
    setPlaying(true);
  }, [cursor, total]);

  const restart = useCallback(() => {
    setCursor(0);
    setPlaying(true);
  }, []);

  const activeIndex = cursor;
  const progressPct = total > 1 ? (cursor / (total - 1)) * 100 : 100;

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-cyan-300/90">
        <Sparkles className="w-4 h-4" />
        BUILD REPLAY
      </div>
      <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight">{build.title}</h1>
      {build.idea && build.idea !== build.title && (
        <p className="mt-2 text-gray-400 max-w-2xl">“{build.idea}”</p>
      )}

      {/* Stat badges */}
      <div className="mt-4 flex flex-wrap gap-2">
        {build.shipped ? (
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-400/30 text-emerald-300">
            <Rocket className="w-3.5 h-3.5" /> Shipped
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-400/30 text-amber-300">
            <Loader2 className="w-3.5 h-3.5" /> In pipeline
          </span>
        )}
        <span className="text-xs px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-gray-300">
          {build.stage_count} agent stages
        </span>
        {build.total_build_seconds ? (
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-gray-300">
            <Clock className="w-3.5 h-3.5" /> {fmtDuration(build.total_build_seconds)} of agent work
          </span>
        ) : null}
        {build.repair_rounds > 0 && (
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-400/30 text-indigo-300">
            <RefreshCw className="w-3.5 h-3.5" /> {build.repair_rounds} repair{build.repair_rounds > 1 ? 's' : ''}
          </span>
        )}
        {build.category && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-gray-400">
            {build.category}
          </span>
        )}
      </div>

      {/* Player controls */}
      <div className="mt-6 flex items-center gap-3">
        {playing ? (
          <button
            onClick={() => setPlaying(false)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/15 border border-cyan-400/30 text-cyan-200 hover:bg-cyan-500/25 transition-colors"
          >
            <Pause className="w-4 h-4" /> Pause
          </button>
        ) : (
          <button
            onClick={play}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/15 border border-cyan-400/30 text-cyan-200 hover:bg-cyan-500/25 transition-colors"
          >
            <Play className="w-4 h-4" /> {cursor >= total - 1 ? 'Replay' : 'Play'}
          </button>
        )}
        <button
          onClick={restart}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-gray-300 hover:bg-white/10 transition-colors"
          aria-label="Restart"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <input
            type="range"
            min={0}
            max={Math.max(0, total - 1)}
            value={cursor}
            onChange={(e) => {
              setPlaying(false);
              setCursor(Number(e.target.value));
            }}
            className="w-full accent-cyan-400 cursor-pointer"
            aria-label="Scrub through build stages"
          />
        </div>
        <span className="text-xs text-gray-500 tabular-nums w-14 text-right">
          {Math.min(cursor + 1, total)}/{total}
        </span>
      </div>

      {/* Progress rail */}
      <div className="mt-3 h-1 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-cyan-400 to-indigo-400"
          animate={{ width: `${progressPct}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Timeline */}
      <ol className="mt-8 space-y-3">
        {stages.map((stage, i) => {
          const revealed = i <= cursor;
          const isActive = i === activeIndex && playing;
          return (
            <AnimatePresence key={`${stage.agent}-${i}`}>
              {revealed && (
                <motion.li
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <GlassCard
                    hover={false}
                    className={`!p-4 border transition-colors ${
                      isActive
                        ? 'border-cyan-400/50 bg-cyan-500/5'
                        : 'border-white/10'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="text-2xl leading-none mt-0.5" aria-hidden>
                        {stage.emoji}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-white">{stage.label}</span>
                          {stage.is_gate && (
                            <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-indigo-500/15 border border-indigo-400/30 text-indigo-300">
                              <ShieldCheck className="w-3 h-3" /> gate
                            </span>
                          )}
                          {stage.retry_count > 0 && (
                            <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 border border-amber-400/30 text-amber-300">
                              <RefreshCw className="w-3 h-3" /> retry ×{stage.retry_count}
                            </span>
                          )}
                        </div>
                        {stage.blurb && <p className="text-sm text-gray-400 mt-0.5">{stage.blurb}</p>}
                        <HighlightChips highlights={stage.highlights} />
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <StatusIcon stage={stage} active={isActive} />
                        {stage.duration_sec ? (
                          <span className="text-[11px] text-gray-500 tabular-nums">
                            {fmtDuration(stage.duration_sec)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </GlassCard>
                </motion.li>
              )}
            </AnimatePresence>
          );
        })}
      </ol>

      {!total && (
        <p className="mt-8 text-gray-500">This build has no recorded stages yet.</p>
      )}

      {/* CTA footer */}
      <div className="mt-12 rounded-2xl border border-white/10 bg-gradient-to-br from-cyan-500/5 to-indigo-500/5 p-6 sm:p-8 text-center">
        <h2 className="text-xl sm:text-2xl font-bold text-white">
          You just watched AI agents {build.shipped ? 'ship' : 'build'} a product.
        </h2>
        <p className="text-gray-400 mt-1">Now point them at your idea — self-hosted, your keys, your infra.</p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition-colors"
          >
            Build your own <ArrowRight className="w-4 h-4" />
          </Link>
          {build.shipped && (
            <Link
              href={build.product_url}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white hover:bg-white/10 transition-colors"
            >
              Open the product <ExternalLink className="w-4 h-4" />
            </Link>
          )}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white hover:bg-white/10 transition-colors"
          >
            <Github className="w-4 h-4" /> Star on GitHub
          </a>
        </div>
        <div className="mt-6">
          <Link href="/builds" className="text-sm text-cyan-300/80 hover:text-cyan-200">
            ← Browse more builds
          </Link>
        </div>
      </div>
    </div>
  );
}
