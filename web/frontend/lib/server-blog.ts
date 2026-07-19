import type { BlogPost } from '@/content/blogPosts';

function apiBase(): string {
  return (
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_INTERNAL_API_URL ||
    'http://127.0.0.1:8081'
  ).replace(/\/$/, '');
}

function normalizePost(raw: Record<string, unknown>): BlogPost | null {
  const slug = String(raw.slug || '').trim();
  const title = String(raw.title || '').trim();
  if (!slug || !title) return null;
  return {
    slug,
    title,
    excerpt: String(raw.excerpt || '').trim(),
    publishedAt: String(raw.publishedAt || '').trim(),
    readTime: String(raw.readTime || '5 min').trim(),
    tags: Array.isArray(raw.tags) ? raw.tags.map((t) => String(t)) : [],
    author: raw.author ? String(raw.author) : undefined,
    relatedProducts: Array.isArray(raw.relatedProducts)
      ? raw.relatedProducts.map((rp) => {
          const row = rp as Record<string, unknown>;
          return {
            productId: String(row.productId || ''),
            label: row.label ? String(row.label) : undefined,
          };
        })
      : undefined,
    body: Array.isArray(raw.body) ? (raw.body as BlogPost['body']) : [],
  };
}

export async function fetchLaunchBlogPosts(): Promise<BlogPost[]> {
  try {
    const res = await fetch(`${apiBase()}/api/blog/posts`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    const data = (await res.json()) as { posts?: Record<string, unknown>[] };
    const out: BlogPost[] = [];
    for (const summary of data.posts || []) {
      const slug = String(summary.slug || '');
      if (!slug) continue;
      out.push({
        slug,
        title: String(summary.title || ''),
        excerpt: String(summary.excerpt || ''),
        publishedAt: String(summary.publishedAt || ''),
        readTime: String(summary.readTime || '5 min'),
        tags: Array.isArray(summary.tags) ? summary.tags.map((t) => String(t)) : [],
        author: summary.author ? String(summary.author) : undefined,
        body: [],
      });
    }
    return out;
  } catch {
    return [];
  }
}

export async function fetchLaunchBlogPost(slug: string): Promise<BlogPost | null> {
  try {
    const res = await fetch(`${apiBase()}/api/blog/posts/${encodeURIComponent(slug)}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return normalizePost((await res.json()) as Record<string, unknown>);
  } catch {
    return null;
  }
}

export function mergeBlogPosts(editorial: BlogPost[], launch: BlogPost[]): BlogPost[] {
  const bySlug = new Map<string, BlogPost>();
  for (const post of editorial) bySlug.set(post.slug, post);
  for (const post of launch) bySlug.set(post.slug, post);
  return [...bySlug.values()].sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));
}
