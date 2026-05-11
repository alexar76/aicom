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
      <p className="text-gray-400 mb-10">
        Product discovery, SEO-friendly launch workflows, and practical growth loops.
      </p>
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
