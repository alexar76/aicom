import type { Metadata } from 'next';
import Link from 'next/link';
import { ScrollText } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import updates from '@/content/updates.json';

export const metadata: Metadata = {
  title: 'Updates',
  description: 'Changelog and product updates for the AI-Factory platform.',
  openGraph: { title: 'AI-Factory Updates', type: 'website' },
};

type Entry = { date: string; title: string; body: string };

export default function UpdatesPage() {
  const rows = updates as Entry[];

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <ScrollText className="w-8 h-8 text-indigo-400" />
        <h1 className="text-3xl font-bold text-white">Updates</h1>
      </div>
      <p className="text-gray-400 text-sm mb-10">
        Highlights from the public storefront and pipeline. For operational detail, see repo docs.
      </p>

      <div className="space-y-4">
        {rows.map((u, i) => (
          <GlassCard key={i}>
            <p className="text-xs text-gray-500 mb-1">{u.date}</p>
            <h2 className="text-lg font-semibold text-white mb-2">{u.title}</h2>
            <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">{u.body}</p>
          </GlassCard>
        ))}
      </div>

      <p className="mt-10 text-center">
        <Link href="/" className="text-sm text-gray-500 hover:text-white">
          ← Home
        </Link>
      </p>
    </div>
  );
}
