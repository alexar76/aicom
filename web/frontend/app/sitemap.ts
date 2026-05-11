import type { MetadataRoute } from 'next';
import { BLOG_POSTS } from '@/content/blogPosts';

const site = (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');

export default function sitemap(): MetadataRoute.Sitemap {
  const core = ['', '/about', '/docs', '/benchmark', '/updates', '/blog', '/launch-kit', '/badge'].map((path) => ({
    url: `${site}${path}`,
    lastModified: new Date(),
    changeFrequency: 'daily' as const,
    priority: path === '' ? 1 : 0.7,
  }));
  const blog = BLOG_POSTS.map((post) => ({
    url: `${site}/blog/${post.slug}`,
    lastModified: new Date(post.publishedAt),
    changeFrequency: 'weekly' as const,
    priority: 0.6,
  }));
  return [...core, ...blog];
}
