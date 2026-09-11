import type { Metadata } from 'next';
import Link from 'next/link';
import { Boxes, Rocket, Loader2, ArrowRight, Clock } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { listBuilds } from '@/lib/server-api';

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: { absolute: 'Build replays — watch AI agents ship products · AI-Factory' },
  description:
    'A live feed of products built by AI-Factory agents. Open any build to replay the pipeline — research, design, code, QA, security — step by step.',
};

function fmtAgo(ts: number | null): string {
  if (!ts) return '';
  const sec = Math.max(0, Date.now() / 1000 - ts);
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

export default async function BuildsGalleryPage() {
  const builds = await listBuilds(36);

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-3">
        <Boxes className="w-7 h-7 text-cyan-400" />
        <h1 className="text-3xl font-bold text-white">Build replays</h1>
      </div>
      <p className="text-gray-400 text-sm mb-8 max-w-2xl">
        Every product here was built by a pipeline of AI agents — research → design → code → QA →
        security → deploy. Open any build to <strong className="text-gray-300">replay it stage by stage</strong>.
      </p>

      {builds.length === 0 ? (
        <GlassCard hover={false} className="text-center py-16">
          <p className="text-gray-400">No builds yet. Be the first —</p>
          <Link
            href="/"
            className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-500 text-slate-950 font-semibold hover:bg-cyan-400 transition-colors"
          >
            Start a build <ArrowRight className="w-4 h-4" />
          </Link>
        </GlassCard>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {builds.map((b) => (
            <Link key={b.id} href={b.replay_url} className="block">
              <GlassCard className="h-full hover:border-cyan-500/30 transition-colors !p-5">
                <div className="flex items-center justify-between mb-2">
                  {b.shipped ? (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-400/30 text-emerald-300">
                      <Rocket className="w-3 h-3" /> shipped
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-400/30 text-amber-300">
                      <Loader2 className="w-3 h-3" /> in pipeline
                    </span>
                  )}
                  <span className="text-[11px] text-gray-500 inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {fmtAgo(b.created_at)}
                  </span>
                </div>
                <h2 className="text-white font-semibold leading-snug line-clamp-2">{b.title}</h2>
                <div className="mt-3 flex items-center gap-2 text-xs text-gray-400">
                  <span>{b.stage_count} stages</span>
                  {b.category && (
                    <>
                      <span className="text-gray-600">·</span>
                      <span>{b.category}</span>
                    </>
                  )}
                </div>
                <div className="mt-3 text-cyan-300/80 text-sm inline-flex items-center gap-1">
                  Watch replay <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </GlassCard>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
