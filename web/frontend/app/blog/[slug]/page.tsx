import { notFound } from 'next/navigation';
import Link from 'next/link';
import { BLOG_POSTS, getPostBySlug, type BlogBodyBlock } from '@/content/blogPosts';
import { fetchLaunchBlogPost } from '@/lib/server-blog';

type PageProps = { params: { slug: string } };

export const dynamic = 'force-dynamic';

export function generateStaticParams() {
  return BLOG_POSTS.map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({ params }: PageProps) {
  const post = (await fetchLaunchBlogPost(params.slug)) ?? getPostBySlug(params.slug);
  if (!post) return { title: 'Post not found' };
  return {
    title: post.title,
    description: post.excerpt,
  };
}

function BlogBody({ blocks }: { blocks: BlogBodyBlock[] }) {
  return (
    <div className="space-y-5 text-gray-200 leading-relaxed">
      {blocks.map((block, idx) => {
        const key = `${idx}-${block.type}`;
        switch (block.type) {
          case 'p':
            return (
              <p key={key} className="text-[1.05rem] text-gray-200/95">
                {block.text}
              </p>
            );
          case 'h2':
            return (
              <h2 key={key} className="text-xl font-semibold text-white mt-10 mb-2 first:mt-0 tracking-tight">
                {block.text}
              </h2>
            );
          case 'quote':
            return (
              <blockquote
                key={key}
                className="border-l-[3px] border-indigo-400/60 pl-5 py-1 my-2 text-gray-300 italic text-[1.05rem]"
              >
                {block.text}
              </blockquote>
            );
          case 'ul':
            return (
              <ul key={key} className="list-disc pl-6 space-y-2 text-gray-200/95 marker:text-indigo-400/80">
                {block.items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            );
          case 'img':
            return (
              <figure key={key} className="my-8">
                <div className="rounded-xl overflow-hidden border border-white/10 bg-black/30 shadow-lg shadow-black/40">
                  {/* eslint-disable-next-line @next/next/no-img-element -- CMS/markdown image with arbitrary remote src and unknown intrinsic dimensions; next/image needs width/height or fill */}
                  <img src={block.src} alt={block.alt} className="w-full h-auto block" loading="lazy" />
                </div>
                {block.caption ? (
                  <figcaption className="mt-3 text-sm text-gray-500 text-center leading-snug px-2">
                    {block.caption}
                  </figcaption>
                ) : null}
              </figure>
            );
          case 'product_link':
            return (
              <div key={key} className="my-6 not-prose">
                <Link
                  href={`/product/${encodeURIComponent(block.productId)}`}
                  className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/35 bg-indigo-500/[0.09] px-4 py-3 text-[1.05rem] font-medium text-indigo-200/95 hover:bg-indigo-500/15 hover:border-indigo-400/45 transition-colors"
                >
                  {block.label ?? 'Product page'}
                  <span aria-hidden className="text-indigo-400/75">
                    →
                  </span>
                </Link>
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

export default async function BlogPostPage({ params }: PageProps) {
  const post = (await fetchLaunchBlogPost(params.slug)) ?? getPostBySlug(params.slug);
  if (!post) notFound();
  return (
    <main className="min-h-screen max-w-3xl mx-auto px-4 py-12 bg-[#060606]">
      <p className="text-xs text-gray-500 mb-3">
        {post.publishedAt}
        {post.author ? ` • ${post.author}` : ''} • {post.readTime}
      </p>
      <h1 className="text-4xl font-bold text-white mb-4 tracking-tight">{post.title}</h1>
      <p className="text-lg text-gray-400 mb-6 leading-relaxed">{post.excerpt}</p>
      {post.relatedProducts && post.relatedProducts.length > 0 ? (
        <div className="flex flex-wrap gap-3 mb-10">
          {post.relatedProducts.map((rp) => (
            <Link
              key={rp.productId}
              href={`/product/${encodeURIComponent(rp.productId)}`}
              className="inline-flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-cyan-500/[0.07] px-4 py-2.5 text-sm font-medium text-cyan-100/95 hover:bg-cyan-500/12 hover:border-cyan-400/40 transition-colors"
            >
              {rp.label ?? 'Product page'}
              <span aria-hidden className="text-cyan-400/70">
                →
              </span>
            </Link>
          ))}
        </div>
      ) : null}
      <BlogBody blocks={post.body} />
    </main>
  );
}
