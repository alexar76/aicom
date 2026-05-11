import Link from 'next/link';
import { BLOG_POSTS } from '@/content/blogPosts';

export const metadata = {
  title: 'AI-Factory Blog',
  description:
    'Growth, product discovery, and AI pipeline execution playbooks for builders shipping faster.',
};

export default function BlogIndexPage() {
  const posts = [...BLOG_POSTS].sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));
  return (
    <main className="min-h-screen max-w-5xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-white mb-3">AI-Factory Blog</h1>
      <p className="text-gray-400 mb-6">
        Product discovery, SEO-friendly launch workflows, and practical growth loops.
      </p>

      <section className="mb-10 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-sm leading-relaxed text-gray-300">
        <h2 className="mb-3 text-base font-semibold text-white">Who writes what?</h2>
        <p className="mb-3">
          Articles here are <strong className="text-gray-200">editorial content checked into the codebase</strong> — not
          anonymous forum posts. Each piece has a title, excerpt, optional <strong className="text-gray-200">author</strong>{' '}
          byline, and structured body blocks (paragraphs, headings, lists, images). Think of it as a lightweight static
          magazine over the same repo that ships the product.
        </p>
        <p className="mb-3">
          <strong className="text-gray-200">Launch / ship posts</strong> (tags like “product launch”) are written to describe
          what went live: narrative plus screenshots under <code className="text-xs text-cyan-300/90">public/blog/</code>, and
          links to real product pages via <code className="text-xs text-cyan-300/90">relatedProducts</code> /{' '}
          <code className="text-xs text-cyan-300/90">product_link</code> blocks — that pattern is already supported in{' '}
          <code className="text-xs text-gray-400">content/blogPosts.ts</code>.
        </p>
        <p className="mb-3">
          <strong className="text-gray-200">Can you tune cadence or turn on “post after product ships”?</strong> Today there is{' '}
          <strong className="text-gray-200">no admin UI</strong> for schedule, quotas, or auto-publishing when a pipeline run
          finishes. Frequency is whatever you commit: add a post when you ship, or batch edits monthly. A future optional flow
          would be: pipeline completes → draft launch post (copy + screenshot hook) → human approves → merge — that checkbox
          does not exist in Settings yet; ship-with-blog remains a manual editorial step after release.
        </p>
      </section>
      <div className="space-y-5">
        {posts.map((post) => (
          <article key={post.slug} className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <p className="text-xs text-gray-500 mb-2">
              {post.publishedAt} • {post.readTime}
            </p>
            <h2 className="text-2xl font-semibold text-white mb-2">
              <Link href={`/blog/${post.slug}`} className="hover:text-indigo-300">
                {post.title}
              </Link>
            </h2>
            <p className="text-gray-300 mb-3 leading-relaxed">{post.excerpt}</p>
            {post.author && (
              <p className="text-xs text-gray-500 mb-3">By {post.author}</p>
            )}
            <div className="flex flex-wrap gap-2">
              {post.tags.map((tag) => (
                <span key={tag} className="text-xs px-2 py-1 rounded-full bg-black/30 text-cyan-300 border border-white/10">
                  {tag}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
