import Link from 'next/link';
import { Layers } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { CATEGORY_EMOJIS, CATEGORY_LABELS, EXPLORE_SLUGS } from '@/lib/categories';
import { getProductsByCategory } from '@/lib/server-api';

export const dynamic = "force-dynamic";

export default async function ExploreIndexPage() {
  const entries = await Promise.all(
    EXPLORE_SLUGS.map(async (slug) => {
      const products = await getProductsByCategory(slug);
      return {
        slug,
        label: CATEGORY_LABELS[slug] || slug,
        emoji: CATEGORY_EMOJIS[slug] || CATEGORY_EMOJIS.uncategorized,
        count: products.length,
      };
    })
  );

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-3">
        <Layers className="w-7 h-7 text-indigo-400" />
        <h1 className="text-3xl font-bold text-white">Explore Categories</h1>
      </div>
      <p className="text-gray-400 text-sm mb-8">
        Use the Landing pages category for brochure landings. SaaS, IoT, and other verticals list runnable apps / full
        builds only — marketing landings are not mixed in there.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((c) => (
          <Link key={c.slug} href={`/explore/${c.slug}`} className="block">
            <GlassCard className="h-full hover:border-indigo-500/30 transition-colors">
              <div className="flex items-center gap-3">
                <span className="text-2xl" aria-hidden>
                  {c.emoji}
                </span>
                <div>
                  <p className="text-white font-medium">{c.label}</p>
                  <p className="text-xs text-gray-400">{c.count} products</p>
                </div>
              </div>
            </GlassCard>
          </Link>
        ))}
      </div>
    </div>
  );
}
