'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Bot, ArrowRight, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import type { FactoryAgentRow, FactoryAgentsRoster } from '@/lib/server-api';

const STATUS_STYLE: Record<string, string> = {
  live: 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10',
  stale: 'text-amber-300 border-amber-400/40 bg-amber-500/10',
  offline: 'text-gray-400 border-gray-600/40 bg-gray-500/10',
};

const POLL_MS = 15_000;

function fmtAge(sec: number): string {
  if (!sec || sec < 60) return `${Math.max(0, Math.round(sec))}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h`;
  return `${Math.round(sec / 86400)}d`;
}

function money(usd: number): string {
  if (!usd) return '$0';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function normalize(data: unknown): FactoryAgentsRoster {
  const empty: FactoryAgentsRoster = {
    agents: [],
    summary: { agents_total: 0, agents_live: 0, invokes_total: 0, spend_usd_total: 0 },
  };
  if (!data || typeof data !== 'object') return empty;
  const doc = data as Record<string, unknown>;
  const agents = Array.isArray(doc.agents) ? doc.agents : [];
  const summary =
    doc.summary && typeof doc.summary === 'object'
      ? (doc.summary as Record<string, unknown>)
      : {};
  return {
    agents: agents.map((raw) => {
      const a = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
      const stats = (a.stats && typeof a.stats === 'object' ? a.stats : {}) as Record<
        string,
        unknown
      >;
      return {
        agent_id: String(a.agent_id || ''),
        name: String(a.name || a.agent_id || ''),
        product_id: String(a.product_id || ''),
        sdk: String(a.sdk || ''),
        version: String(a.version || ''),
        public_url: String(a.public_url || ''),
        status: String(a.status || 'offline'),
        verified: Boolean(a.verified),
        age_sec: Number(a.age_sec || 0),
        capabilities_used: Array.isArray(a.capabilities_used)
          ? a.capabilities_used.map((c) => String(c))
          : [],
        invokes_total: Number(stats.invokes_total || 0),
        spend_usd_total: Number(stats.spend_usd_total || 0),
      } satisfies FactoryAgentRow;
    }),
    summary: {
      agents_total: Number(summary.agents_total || agents.length),
      agents_live: Number(summary.agents_live || 0),
      invokes_total: Number(summary.invokes_total || 0),
      spend_usd_total: Number(summary.spend_usd_total || 0),
      sdks: summary.sdks as Record<string, number> | undefined,
      capabilities: summary.capabilities as Record<string, number> | undefined,
    },
  };
}

type Props = { initial: FactoryAgentsRoster };

export function FactoryAgentsRosterClient({ initial }: Props) {
  const [roster, setRoster] = useState(initial);
  const [updatedAt, setUpdatedAt] = useState<number>(() => Date.now());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/agents?include_offline=true', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRoster(normalize(await res.json()));
      setUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'refresh failed');
    }
  }, []);

  useEffect(() => {
    const id = window.setInterval(refresh, POLL_MS);
    const onVis = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [refresh]);

  const sorted = [...roster.agents].sort((a, b) => {
    const rank = (s: string) => (s === 'live' ? 0 : s === 'stale' ? 1 : 2);
    return rank(a.status) - rank(b.status) || b.spend_usd_total - a.spend_usd_total;
  });
  const sdks = Object.entries(roster.summary.sdks || {});

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-3">
        <Bot className="w-7 h-7 text-cyan-400" />
        <h1 className="text-3xl font-bold text-white font-[family-name:var(--font-display,Space_Grotesk)]">
          Factory agents
        </h1>
      </div>
      <p className="text-gray-400 text-sm mb-6 max-w-2xl">
        Products the factory ships as <strong className="text-gray-300">autonomous agents</strong> — they
        keep running after release, invoke AIMarket capabilities, and heartbeat counters here. JSON
        API:{' '}
        <Link href="/api/agents" className="text-cyan-400/90 hover:text-cyan-300 underline">
          /api/agents
        </Link>
        .
      </p>

      <div className="mb-4 px-4 py-3 rounded-xl border border-cyan-500/20 bg-cyan-500/5 text-sm font-mono flex flex-wrap gap-x-4 gap-y-1 text-cyan-200/90">
        <span>
          {roster.summary.agents_live}/{roster.summary.agents_total} live
        </span>
        <span>{roster.summary.invokes_total.toLocaleString()} invokes</span>
        <span>{money(roster.summary.spend_usd_total)} spent</span>
      </div>

      {sdks.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {sdks.map(([k, v]) => (
            <span
              key={k}
              className="text-[11px] font-mono px-2.5 py-0.5 rounded-full border border-cyan-400/25 bg-cyan-500/10 text-cyan-100/90"
            >
              {k} · {v}
            </span>
          ))}
        </div>
      )}

      <div className="mb-6 flex items-center gap-2 text-xs font-mono text-gray-500">
        <RefreshCw className={`w-3.5 h-3.5 ${error ? 'text-rose-400' : 'text-emerald-400'}`} />
        {error
          ? `refresh failed · ${error}`
          : `auto-refresh · updated ${fmtAge((Date.now() - updatedAt) / 1000)} ago`}
      </div>

      {sorted.length === 0 ? (
        <GlassCard hover={false} className="text-center py-16">
          <p className="text-gray-400">No agents registered yet.</p>
          <Link
            href="/"
            className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition-colors"
          >
            Start a build <ArrowRight className="w-4 h-4" />
          </Link>
        </GlassCard>
      ) : (
        <div className="grid gap-3">
          {sorted.map((a) => (
            <GlassCard key={a.agent_id} hover={false} className="group !p-5">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
                <div className="min-w-0 flex-1">
                  <h2
                    className="text-white font-semibold leading-snug break-words line-clamp-2 group-hover:line-clamp-none"
                    title={a.name}
                  >
                    {a.name}
                  </h2>
                  <p
                    className="text-xs text-gray-500 font-mono mt-0.5 leading-snug break-all line-clamp-2 group-hover:line-clamp-none"
                    title={a.agent_id}
                  >
                    {a.agent_id}
                  </p>
                </div>
                <span
                  className={`text-[11px] px-2 py-0.5 rounded-full border font-mono ${STATUS_STYLE[a.status] || STATUS_STYLE.offline}`}
                >
                  {a.status} · {fmtAge(a.age_sec)} ago
                </span>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 font-mono mb-3">
                {a.product_id && (
                  <Link href={`/product/${a.product_id}`} className="text-cyan-400/80 hover:text-cyan-300">
                    {a.product_id}
                  </Link>
                )}
                {a.sdk && <span>sdk {a.sdk}</span>}
                {a.version && <span>v{a.version}</span>}
                <span>{a.invokes_total} invokes</span>
                <span>{money(a.spend_usd_total)}</span>
              </div>
              {a.capabilities_used.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {a.capabilities_used.map((cap) => (
                    <span
                      key={cap}
                      className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/30 border border-gray-700/50 text-gray-400"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              )}
              {a.public_url && (
                <a
                  href={a.public_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 text-sm text-cyan-400/80 hover:text-cyan-300 inline-flex items-center gap-1"
                >
                  {a.public_url} <ArrowRight className="w-3.5 h-3.5" />
                </a>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
