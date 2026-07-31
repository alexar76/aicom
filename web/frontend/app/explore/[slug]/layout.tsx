import type { Metadata } from 'next';
import { CATEGORY_LABELS, EXPLORE_SLUGS } from '@/lib/categories';

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');
}

export async function generateStaticParams() {
  return EXPLORE_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const label = CATEGORY_LABELS[params.slug] || params.slug;
  const title = `${label} products`;
  const fullTitle = `${title} — AI-Factory`;
  const description = `Explore autonomous AI-Factory products in the ${label} category.`;
  const url = `${siteUrl()}/explore/${params.slug}`;

  return {
    title: { absolute: fullTitle },
    description,
    openGraph: { title: fullTitle, description, url, type: 'website' },
    twitter: { card: 'summary_large_image', title: fullTitle, description },
    alternates: { canonical: url },
  };
}

export default function ExploreLayout({ children }: { children: React.ReactNode }) {
  return children;
}
