import type { MetadataRoute } from 'next';
import { BLOG_POSTS } from '@/content/blogPosts';
import { listBuilds } from '@/lib/server-api';

const site = (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const core = ['', '/about', '/docs', '/benchmark', '/updates', '/blog', '/launch-kit', '/badge', '/builds'].map(
    (path) => ({
      url: `${site}${path}`,
      lastModified: new Date(),
      changeFrequency: 'daily' as const,
      priority: path === '' ? 1 : 0.7,
    }),
  );
  const blog = BLOG_POSTS.map((post) => ({
    url: `${site}/blog/${post.slug}`,
    lastModified: new Date(post.publishedAt),
    changeFrequency: 'weekly' as const,
    priority: 0.6,
  }));
  // Shareable build replays — best-effort; never block the sitemap on the API.
  let builds: MetadataRoute.Sitemap = [];
  try {
    const recent = await listBuilds(50);
    builds = recent.map((b) => ({
      url: `${site}/build/${b.id}`,
      lastModified: b.created_at ? new Date(b.created_at * 1000) : new Date(),
      changeFrequency: 'weekly' as const,
      priority: 0.5,
    }));
  } catch {
    builds = [];
  }
  return [...core, ...blog, ...builds];
}
