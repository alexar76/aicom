'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  Coins,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { PublicMarketingNav } from '@/components/marketing/PublicMarketingNav';
import { FactoryIqBrainScene } from '@/components/iq/FactoryIqBrainScene';
import {
  CalibrationMeter,
  CompareBars,
  EvAreaChart,
  IqGaugeRing,
} from '@/components/iq/FactoryIqCharts';
import { detectMarketingLocale, type MarketingLocale } from '@/lib/marketing';
import { getFactoryIqStrings } from '@/lib/marketing-iq';

interface IQSnapshot {
  factory_iq: number | null;
  learning_curve: {
    live_ev_mean: number;
    frozen_ev_mean: number | null;
    gap: number | null;
    paying_off: boolean;
    ev_series: number[];
  };
  ship_rate: number;
  cost_per_ship: number;
  ev_slope: number;
  builds: { live: number; frozen: number };
  playbook: { active_rules: number; total_rules: number; rule_mean_lift: number };
  calibration?: { overall_calibration_error: number; samples: number };
  recent_rules: Array<{
    claim: string;
    category: string | null;
    lift_ev: number;
    confidence: number;
    win_rate: number;
    support: number;
  }>;
}

function Stat({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <GlassCard hover={false} className="p-4 border border-white/10 bg-gradient-to-br from-white/[0.06] to-transparent">
      <div className="flex items-center gap-2 text-gray-400 text-xs uppercase tracking-wide">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-white tabular-nums">{value}</div>
      {hint && <div className="text-xs text-gray-500 mt-0.5">{hint}</div>}
    </GlassCard>
  );
}

export default function FactoryIqPage() {
  const [locale, setLocale] = useState<MarketingLocale>('en');
  const [snap, setSnap] = useState<IQSnapshot | null>(null);
  const [err, setErr] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const copy = getFactoryIqStrings(locale);

  useEffect(() => {
    setLocale(detectMarketingLocale());
    const sync = () => setLocale(detectMarketingLocale());
    window.addEventListener('marketing-locale-changed', sync);
    return () => window.removeEventListener('marketing-locale-changed', sync);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch('/api/analytics/factory-iq', { cache: 'no-store' });
        if (!res.ok) throw new Error(String(res.status));
        setSnap(await res.json());
        setErr(false);
      } catch {
        setErr(true);
      }
    };
    load();
    timer.current = setInterval(load, 15000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  const iq = snap?.factory_iq ?? null;
  const lc = snap?.learning_curve;
  const modelCount = copy.swarmNodes.length;

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.12),transparent_50%),radial-gradient(ellipse_at_bottom_right,rgba(34,211,238,0.08),transparent_45%)]">
      <PublicMarketingNav activePath="/iq" />

      <div className="px-4 py-8 pt-24 max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-300/90 mb-2">{copy.eyebrow}</p>
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <h1 className="text-3xl sm:text-4xl font-bold text-white">{copy.pageTitle}</h1>
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-medium text-emerald-200">
              <Zap className="w-3 h-3" />
              {copy.livePulse}
            </span>
          </div>
          <p className="text-gray-400 text-sm max-w-3xl leading-relaxed">{copy.subtitle}</p>
        </motion.div>

        {err && !snap && (
          <GlassCard hover={false} className="text-center py-12 text-gray-400 mb-6">
            {copy.unavailable}
          </GlassCard>
        )}

        <div className="grid lg:grid-cols-[1fr_1.1fr] gap-6 mb-6">
          <GlassCard hover={false} className="p-6 border border-cyan-500/20 bg-gradient-to-b from-cyan-950/20 to-transparent overflow-hidden">
            <h2 className="text-sm font-semibold text-gray-200 mb-1">{copy.swarmTitle}</h2>
            <p className="text-xs text-gray-500 mb-4 max-w-md">{copy.swarmSubtitle}</p>
            <FactoryIqBrainScene copy={copy} iq={iq} modelCount={modelCount} />
            <p className="text-center text-xs text-gray-500 mt-2">
              {snap ? copy.buildsLiveFrozen(snap.builds.live, snap.builds.frozen) : '…'}
            </p>
          </GlassCard>

          <div className="space-y-4">
            <GlassCard hover={false} className="p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <IqGaugeRing iq={iq} label={copy.heroIqLabel} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-gray-300 text-sm font-semibold">
                      <Activity className="w-4 h-4 text-cyan-400" />
                      {copy.learningCurve}
                    </div>
                    {lc?.gap != null && (
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
                          lc.paying_off ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'
                        }`}
                      >
                        {lc.paying_off ? copy.payingOff(lc.gap.toFixed(2)) : copy.notPayingOff}
                      </span>
                    )}
                  </div>
                  <EvAreaChart values={lc?.ev_series ?? []} emptyLabel={copy.noBuildsYet} />
                  <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-400">
                    <span>
                      {copy.liveMean}: <span className="text-white">{lc ? lc.live_ev_mean.toFixed(2) : '—'}</span>
                    </span>
                    <span>
                      {copy.frozenControl}:{' '}
                      <span className="text-white">
                        {lc?.frozen_ev_mean != null ? lc.frozen_ev_mean.toFixed(2) : 'n/a'}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            </GlassCard>

            <GlassCard hover={false} className="p-5">
              <div className="text-xs uppercase tracking-wide text-gray-400 mb-3">{copy.chartEvPerBuild}</div>
              <CompareBars
                copy={copy}
                liveMean={lc?.live_ev_mean ?? 0}
                frozenMean={lc?.frozen_ev_mean ?? null}
              />
            </GlassCard>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <Stat
            icon={
              snap && snap.ev_slope >= 0 ? (
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5 text-amber-400" />
              )
            }
            label={copy.evTrend}
            value={snap ? (snap.ev_slope >= 0 ? `+${snap.ev_slope.toFixed(2)}` : snap.ev_slope.toFixed(2)) : '—'}
            hint={copy.evTrendHint}
          />
          <Stat
            icon={<ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />}
            label={copy.shipRate}
            value={snap ? `${Math.round(snap.ship_rate * 100)}%` : '—'}
          />
          <Stat
            icon={<Coins className="w-3.5 h-3.5 text-violet-400" />}
            label={copy.costPerShip}
            value={snap ? `$${snap.cost_per_ship.toFixed(2)}` : '—'}
          />
          <Stat
            icon={<Sparkles className="w-3.5 h-3.5 text-cyan-400" />}
            label={copy.activeRules}
            value={snap ? String(snap.playbook.active_rules) : '—'}
            hint={snap ? copy.meanLift(snap.playbook.rule_mean_lift.toFixed(2)) : undefined}
          />
        </div>

        <div className="grid md:grid-cols-[1.4fr_1fr] gap-4 mb-8">
          <GlassCard hover={false} className="p-6">
            <div className="flex items-center gap-2 text-gray-300 text-sm font-semibold mb-3">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              {copy.playbookTitle}
            </div>
            {snap && snap.recent_rules.length > 0 ? (
              <ul className="space-y-2">
                {snap.recent_rules.map((r, i) => (
                  <motion.li
                    key={r.claim + i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="flex items-center justify-between gap-3 rounded-lg bg-white/5 border border-white/5 px-3 py-2"
                  >
                    <div className="text-sm text-gray-200">
                      {r.category && <span className="text-cyan-400/80 text-xs mr-2">[{r.category}]</span>}
                      {r.claim}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-400 shrink-0">
                      <span className="text-emerald-300">+{r.lift_ev.toFixed(2)} EV</span>
                      <span>{(r.confidence * 100).toFixed(0)}%</span>
                      <span>n={r.support}</span>
                    </div>
                  </motion.li>
                ))}
              </ul>
            ) : (
              <div className="text-gray-500 text-sm">{copy.playbookEmpty}</div>
            )}
          </GlassCard>

          {snap?.calibration && snap.calibration.samples > 0 ? (
            <CalibrationMeter
              copy={copy}
              error={snap.calibration.overall_calibration_error}
              samples={snap.calibration.samples}
            />
          ) : (
            <GlassCard hover={false} className="p-6 flex items-center justify-center text-gray-500 text-sm">
              {copy.gatekeeperHint}
            </GlassCard>
          )}
        </div>

        <Link href="/" className="text-indigo-300 hover:text-indigo-200 text-sm">
          {copy.backHome}
        </Link>
      </div>
    </div>
  );
}
