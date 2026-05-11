'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import { formatBenchmarkRate, formatBenchmarkTrend } from '@/lib/formatBenchmark';

export default function BenchmarkPage() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getPublicBenchmark().then(setData).catch((e: any) => setErr(e?.message || 'Failed to load benchmark'));
  }, []);

  const investor = data?.investor_metrics || {};
  const ci = investor?.confidence_interval_95;
  const ciLow = ci?.low;
  const ciHigh = ci?.high;
  const ciFmt =
    ciLow !== undefined && ciHigh !== undefined
      ? `[${formatBenchmarkRate(ciLow)}, ${formatBenchmarkRate(ciHigh)}] (n=${ci?.n ?? '—'})`
      : '—';
  return (
    <main className="min-h-screen px-4 py-12 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-white mb-2">Benchmark Scoreboard</h1>
      <p className="text-gray-400 mb-8">Transparent quality metrics for pipeline reliability.</p>
      {err && <p className="text-red-400">{err}</p>}
      {!err && !data && <p className="text-gray-400">Loading…</p>}
      {data && (
        <>
          <p className="text-xs text-gray-500 mb-4">
            Source:{' '}
            <span className="text-gray-300">
              {data.investor_metrics_source === 'pipeline_storefront_proxy'
                ? 'storefront readiness proxy (no benchmark league scorecard runs yet)'
                : data.investor_metrics_source === 'pipeline_storefront_proxy_supplement'
                  ? 'storefront readiness proxy (scorecard runs exist but reported pass rates are 0)'
                  : 'benchmark scorecard'}
            </span>
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Stat label="Latest pass rate" value={formatBenchmarkRate(investor.latest_pass_rate)} />
            <Stat label="Rolling 24h" value={formatBenchmarkRate(investor.rolling_24h_pass_rate)} />
            <Stat label="Rolling 7d" value={formatBenchmarkRate(investor.rolling_7d_pass_rate)} />
            <Stat label="Trend vs 7d" value={formatBenchmarkTrend(investor.trend_vs_7d)} />
            <Stat label="Readiness index" value={formatBenchmarkRate(investor.production_readiness_index)} />
            <Stat label="95% CI" value={ciFmt} raw />
          </div>
        </>
      )}
      <div className="mt-8">
        <Link href="/" className="text-indigo-300 hover:text-indigo-200">
          ← Back to homepage
        </Link>
      </div>
    </main>
  );
}

function Stat({ label, value, raw }: { label: string; value: any; raw?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`text-2xl font-semibold text-cyan-300 ${raw ? 'text-base leading-snug' : ''}`}>
        {String(value ?? '—')}
      </p>
    </div>
  );
}
