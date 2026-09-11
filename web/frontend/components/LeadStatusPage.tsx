'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2, CheckCircle2, Clock, AlertCircle, ExternalLink } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';

type LeadStatus = {
  status: string;
  idea_preview?: string;
  product_id?: string;
  product_state?: string;
  product_name?: string;
  sandbox_ready?: boolean;
  storefront_url?: string;
  email?: string;
};

const STATE_LABELS: Record<string, string> = {
  received: 'Received',
  pipeline_started: 'Building',
  completed: 'Ready',
  failed: 'Needs attention',
};

export default function LeadStatusPage({ token }: { token: string }) {
  const [data, setData] = useState<LeadStatus | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetch(`/api/marketing/lead/status/${encodeURIComponent(token)}`)
        .then(async (r) => {
          if (!r.ok) throw new Error('Not found');
          return r.json() as Promise<LeadStatus>;
        })
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setError('');
          }
        })
        .catch(() => {
          if (!cancelled) setError('Status not found');
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };
    load();
    const id = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-400 gap-2">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading status…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen px-4 py-24 max-w-lg mx-auto text-center">
        <AlertCircle className="w-10 h-10 text-amber-400 mx-auto mb-4" />
        <p className="text-white">{error || 'Unknown error'}</p>
        <Link href="/" className="text-indigo-300 text-sm mt-6 inline-block">
          Back to home
        </Link>
      </div>
    );
  }

  const status = data.status || 'received';
  const Icon =
    status === 'completed' ? CheckCircle2 : status === 'failed' ? AlertCircle : Clock;
  const iconClass =
    status === 'completed'
      ? 'text-emerald-400'
      : status === 'failed'
        ? 'text-amber-400'
        : 'text-indigo-400';

  return (
    <div className="min-h-screen px-4 py-20 max-w-xl mx-auto">
      <GlassCard className="text-center py-10">
        <Icon className={`w-12 h-12 mx-auto mb-4 ${iconClass}`} />
        <h1 className="text-2xl font-bold text-white mb-1">{STATE_LABELS[status] || status}</h1>
        <p className="text-gray-400 text-sm mb-6">{data.email}</p>
        {data.idea_preview && (
          <p className="text-gray-300 text-sm mb-6 italic">&ldquo;{data.idea_preview}&rdquo;</p>
        )}
        {data.product_state && (
          <p className="text-xs text-gray-500 mb-4">Pipeline: {data.product_state}</p>
        )}
        {data.storefront_url && (data.sandbox_ready || status === 'completed') && (
          <a
            href={data.storefront_url}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
          >
            View product
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
        {status === 'pipeline_started' && (
          <p className="text-xs text-gray-500 mt-6">This page refreshes every 15 seconds.</p>
        )}
      </GlassCard>
      <p className="text-center mt-8">
        <Link href="/" className="text-sm text-indigo-300 hover:text-indigo-200">
          Back to home
        </Link>
      </p>
    </div>
  );
}
