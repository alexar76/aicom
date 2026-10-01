import Link from 'next/link';
import { ProductNavLink } from '@/components/storefront/ProductNavLink';
import { notFound } from 'next/navigation';
import { ArrowLeft, Package } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Badge } from '@/components/ui/Badge';
import { CATEGORY_EMOJIS, CATEGORY_LABELS, EXPLORE_SLUGS } from '@/lib/categories';
import { getProductsByCategory } from '@/lib/server-api';
import { getStateLabel } from '@/lib/utils';

export const dynamic = "force-dynamic";

export default async function ExploreCategoryPage({
  params,
}: {
  // Next 16: awaiting is not optional — see the note in this segment's layout.
  params: Promise<{ slug: string }>;
}) {
  const { slug: categorySlug } = await params;
  if (!EXPLORE_SLUGS.includes(categorySlug)) {
    notFound();
  }

  const label = CATEGORY_LABELS[categorySlug];
  const emoji = CATEGORY_EMOJIS[categorySlug] ?? CATEGORY_EMOJIS.uncategorized;
  const products = await getProductsByCategory(categorySlug);

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-5xl mx-auto">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-8"
      >
        <ArrowLeft className="w-4 h-4" />
        Home
      </Link>

      <div className="flex items-center gap-3 mb-2">
        <span className="text-3xl" aria-hidden>
          {emoji}
        </span>
        <h1 className="text-3xl font-bold text-white">{label}</h1>
      </div>
      <p className="text-gray-400 text-sm mb-10">
        {categorySlug === 'landings' ? (
          <>
            Marketing landings and promo sites — static brochure builds, not full SaaS/apps.{' '}
            {products.length} product{products.length === 1 ? '' : 's'}.
          </>
        ) : (
          <>
            Runnable apps and full builds in this vertical (marketing landings live under Landing pages).{' '}
            {products.length} product{products.length === 1 ? '' : 's'}.
          </>
        )}
      </p>

      <div className="flex flex-wrap gap-2 mb-8">
        {EXPLORE_SLUGS.map((slug) => {
          const active = slug === categorySlug;
          return (
            <Link
              key={slug}
              href={`/explore/${slug}`}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                active
                  ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-200'
                  : 'bg-white/5 border-white/10 text-gray-300 hover:border-indigo-500/30 hover:text-white'
              }`}
            >
              {(CATEGORY_EMOJIS[slug] ?? '📁')} {CATEGORY_LABELS[slug] ?? slug}
            </Link>
          );
        })}
      </div>

      {products.length === 0 ? (
        <GlassCard className="text-center py-12 text-gray-400">
          <Package className="w-10 h-10 mx-auto mb-3 opacity-50" />
          No products in this category yet.
        </GlassCard>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {products.map((p) => (
            <li key={p.id}>
              <ProductNavLink href={`/product/${p.id}`} className="block">
                <GlassCard className="h-full hover:border-indigo-500/30 transition-colors">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h2 className="text-lg font-semibold text-white line-clamp-2">
                      {p.name || p.idea?.slice(0, 80) || p.id}
                    </h2>
                    <div className="flex flex-col items-end gap-1 shrink-0 max-w-[48%]">
                      <Badge variant="info" className="text-[10px]">
                        {getStateLabel(p.state)}
                      </Badge>
                      {p.delivery_profile === 'marketing_landing' ? (
                        <Badge variant="default" className="text-[10px]">
                          Landing page
                        </Badge>
                      ) : p.delivery_profile ? (
                        <Badge variant="success" className="text-[10px]">
                          Full product
                        </Badge>
                      ) : null}
                      {p.storefront_stack_label ? (
                        <span
                          className="text-[10px] text-gray-500 text-right line-clamp-2 leading-tight"
                          title={p.storefront_stack_label}
                        >
                          {p.storefront_stack_label}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {p.selling_description && (
                    <p className="text-sm text-gray-400 line-clamp-3">{p.selling_description}</p>
                  )}
                </GlassCard>
              </ProductNavLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
