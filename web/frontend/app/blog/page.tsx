import Link from 'next/link';
import { BLOG_POSTS } from '@/content/blogPosts';
import { fetchLaunchBlogPosts, mergeBlogPosts } from '@/lib/server-blog';

export const metadata = {
  title: 'AI-Factory Blog',
  description:
    'Growth, product discovery, and AI pipeline execution playbooks for builders shipping faster.',
};

export const dynamic = 'force-dynamic';

export default async function BlogIndexPage() {
  const launchPosts = await fetchLaunchBlogPosts();
  const posts = mergeBlogPosts(BLOG_POSTS, launchPosts);
  return (
    <main className="min-h-screen max-w-5xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-white mb-3">AI-Factory Blog</h1>
      <p className="text-gray-400 mb-6">
        Product discovery, SEO-friendly launch workflows, and practical growth loops.
      </p>

      <section className="mb-10 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-sm leading-relaxed text-gray-300">
        <h2 className="mb-3 text-base font-semibold text-white">Who writes what?</h2>
        <p className="mb-3">
          <strong className="text-gray-200">Launch posts</strong> are written by the{' '}
          <strong className="text-gray-200">Marketing agent</strong> when a product pipeline reaches{' '}
          <code className="text-xs text-cyan-300/90">COMPLETED</code> — stored under{' '}
          <code className="text-xs text-cyan-300/90">data/blog/</code> and served from{' '}
          <code className="text-xs text-cyan-300/90">/api/blog/posts</code>.
        </p>
        <p className="mb-3">
          <strong className="text-gray-200">Editorial playbooks</strong> (growth, discovery, monetization) are
          human-authored and versioned in{' '}
          <code className="text-xs text-gray-400">content/blogPosts.ts</code>.
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
            {post.author && <p className="text-xs text-gray-500 mb-3">By {post.author}</p>}
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
