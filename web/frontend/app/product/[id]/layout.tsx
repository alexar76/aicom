import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { isProductId } from '@/lib/productId';
import { getProductForMetadata } from '@/lib/server-api';

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');
}

export async function generateMetadata({
  params,
}: {
  // Next 16: `params` is a Promise; reading `.id` without awaiting yields undefined, which
  // stripped every product page of its metadata and rendered it as a 404.
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  if (!isProductId(id)) return {};
  const product = await getProductForMetadata(id);
  const titleBase =
    product?.name ||
    (product?.spec as { product_name?: string } | undefined)?.product_name ||
    product?.idea?.slice(0, 80) ||
    'Product';
  const description =
    product?.selling_description ||
    product?.idea?.slice(0, 160) ||
    'Autonomous software product built by AI-Factory.';
  const url = `${siteUrl()}/product/${id}`;

  return {
    title: { absolute: `${titleBase} — AI-Factory` },
    description,
    openGraph: {
      title: `${titleBase} — AI-Factory`,
      description,
      url,
      type: 'website',
      siteName: 'AI-Factory',
    },
    twitter: {
      card: 'summary_large_image',
      title: `${titleBase} — AI-Factory`,
      description,
    },
    alternates: { canonical: url },
  };
}

// A malformed id answers 404, so search engines drop it. A well-formed id whose product the API
// cannot load right now keeps rendering: a backend hiccup must not unlist a real product.
export default async function ProductSegmentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!isProductId(id)) notFound();
  return children;
}
