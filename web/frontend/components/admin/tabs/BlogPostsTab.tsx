'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Loader2, Newspaper, RefreshCw, Save, Camera } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import api from '@/lib/api';
import { type AdminLocale, t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

type BlogSummary = {
  slug: string;
  title: string;
  excerpt?: string;
  publishedAt?: string;
  status?: string;
  productId?: string;
  source?: string;
};

type BlogPostFull = BlogSummary & {
  readTime?: string;
  tags?: string[];
  author?: string;
  body?: unknown[];
  source?: string;
  editedAt?: string;
  includeScreenshot?: boolean;
};

export function BlogPostsTab({ locale }: { locale: AdminLocale }) {
  const [posts, setPosts] = useState<BlogSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [draft, setDraft] = useState<BlogPostFull | null>(null);
  const [bodyJson, setBodyJson] = useState('');
  const [saving, setSaving] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getAdminBlogPosts();
      const list = (r.posts || []) as BlogSummary[];
      setPosts(list);
      return list;
    } catch {
      setPosts([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPost = useCallback(async (slug: string) => {
    try {
      const post = (await api.getAdminBlogPost(slug)) as BlogPostFull;
      setDraft(post);
      setBodyJson(JSON.stringify(post.body || [], null, 2));
      setSelectedSlug(slug);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to load post');
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const backfill = async () => {
    setBackfilling(true);
    try {
      const r = await api.backfillAdminBlogPosts({ only_missing: true, capture_screenshots: false });
      toast.success(`${t(locale, 'blog.backfillDone')}: ${r.published}`);
      await loadList();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Backfill failed');
    } finally {
      setBackfilling(false);
    }
  };

  const save = async () => {
    if (!selectedSlug || !draft) return;
    let body: unknown[];
    try {
      body = JSON.parse(bodyJson) as unknown[];
      if (!Array.isArray(body)) throw new Error('Body must be a JSON array');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Invalid body JSON');
      return;
    }
    setSaving(true);
    try {
      const tags = String(draft.tags || [])
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);
      const updated = await api.updateAdminBlogPost(selectedSlug, {
        title: draft.title,
        excerpt: draft.excerpt,
        readTime: draft.readTime,
        status: draft.status as 'published' | 'draft',
        publishedAt: draft.publishedAt,
        author: draft.author,
        tags,
        body,
      });
      setDraft(updated as BlogPostFull);
      setBodyJson(JSON.stringify((updated as BlogPostFull).body || [], null, 2));
      toast.success(t(locale, 'blog.saved'));
      await loadList();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const captureScreenshot = async () => {
    if (!selectedSlug) return;
    setCapturing(true);
    try {
      const updated = await api.captureAdminBlogScreenshot(selectedSlug);
      setDraft(updated as BlogPostFull);
      setBodyJson(JSON.stringify((updated as BlogPostFull).body || [], null, 2));
      toast.success(t(locale, 'blog.screenshotDone'));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t(locale, 'blog.screenshotFailed'));
    } finally {
      setCapturing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Newspaper className="h-5 w-5 text-amber-400" />
            {t(locale, 'tab.blog')}
          </h2>
          <p className="text-xs text-gray-500 mt-1">{t(locale, 'blog.intro')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" disabled={loading} onClick={() => void loadList()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button disabled={backfilling} onClick={() => void backfill()}>
            {backfilling ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t(locale, 'blog.backfill')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(240px,320px)_1fr] gap-4">
        <GlassCard className="p-3 max-h-[70vh] overflow-y-auto">
          {loading ? (
            <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mx-auto my-8" />
          ) : posts.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">{t(locale, 'blog.noPosts')}</p>
          ) : (
            <ul className="space-y-1">
              {posts.map((p) => (
                <li key={p.slug}>
                  <button
                    type="button"
                    onClick={() => void loadPost(p.slug)}
                    className={`w-full text-left rounded-lg px-3 py-2 text-sm transition-colors ${
                      selectedSlug === p.slug
                        ? 'bg-indigo-500/20 text-white border border-indigo-500/30'
                        : 'text-gray-300 hover:bg-white/5 border border-transparent'
                    }`}
                  >
                    <div className="font-medium truncate">{p.title}</div>
                    <div className="text-[11px] text-gray-500 mt-0.5 truncate">
                      {p.publishedAt} · {p.productId || p.slug}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>

        <GlassCard className="p-4">
          {!draft ? (
            <p className="text-sm text-gray-500 text-center py-16">{t(locale, 'blog.selectPost')}</p>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {draft.status === 'draft' ? (
                  <Badge variant="warning">{t(locale, 'blog.draft')}</Badge>
                ) : (
                  <Badge variant="success">{t(locale, 'blog.published')}</Badge>
                )}
                <Badge variant="info">
                  {draft.source === 'admin_edited' ? t(locale, 'blog.editedByAdmin') : t(locale, 'blog.fromMarketing')}
                </Badge>
                {draft.productId && (
                  <Link
                    href={`/product/${encodeURIComponent(draft.productId)}`}
                    className="text-xs text-indigo-300 hover:underline"
                  >
                    {t(locale, 'blog.product')}: {draft.productId}
                  </Link>
                )}
                <Link
                  href={`/blog/${encodeURIComponent(draft.slug)}`}
                  target="_blank"
                  className="ml-auto text-xs text-gray-400 hover:text-white inline-flex items-center gap-1"
                >
                  {t(locale, 'blog.preview')}
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </div>

              <label className="block text-xs text-gray-400">
                Title
                <input
                  className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white"
                  value={draft.title || ''}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                />
              </label>

              <label className="block text-xs text-gray-400">
                Excerpt
                <textarea
                  className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white min-h-[72px]"
                  value={draft.excerpt || ''}
                  onChange={(e) => setDraft({ ...draft, excerpt: e.target.value })}
                />
              </label>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <label className="block text-xs text-gray-400">
                  {t(locale, 'blog.status')}
                  <select
                    className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-2 py-2 text-sm text-white"
                    value={draft.status || 'published'}
                    onChange={(e) => setDraft({ ...draft, status: e.target.value })}
                  >
                    <option value="published">{t(locale, 'blog.published')}</option>
                    <option value="draft">{t(locale, 'blog.draft')}</option>
                  </select>
                </label>
                <label className="block text-xs text-gray-400">
                  Published
                  <input
                    className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-2 py-2 text-sm text-white"
                    value={draft.publishedAt || ''}
                    onChange={(e) => setDraft({ ...draft, publishedAt: e.target.value })}
                  />
                </label>
                <label className="block text-xs text-gray-400">
                  Read time
                  <input
                    className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-2 py-2 text-sm text-white"
                    value={draft.readTime || ''}
                    onChange={(e) => setDraft({ ...draft, readTime: e.target.value })}
                  />
                </label>
                <label className="block text-xs text-gray-400">
                  Author
                  <input
                    className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-2 py-2 text-sm text-white"
                    value={draft.author || ''}
                    onChange={(e) => setDraft({ ...draft, author: e.target.value })}
                  />
                </label>
              </div>

              <label className="block text-xs text-gray-400">
                Tags (comma-separated)
                <input
                  className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white"
                  value={Array.isArray(draft.tags) ? draft.tags.join(', ') : ''}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      tags: e.target.value.split(',').map((x) => x.trim()),
                    })
                  }
                />
              </label>

              <label className="block text-xs text-gray-400">
                {t(locale, 'blog.bodyJson')}
                <textarea
                  className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-xs text-white font-mono min-h-[240px]"
                  value={bodyJson}
                  onChange={(e) => setBodyJson(e.target.value)}
                />
              </label>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button disabled={saving} onClick={() => void save()}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {t(locale, 'blog.save')}
                </Button>
                {draft.productId && (
                  <Button variant="secondary" disabled={capturing} onClick={() => void captureScreenshot()}>
                    {capturing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
                    {t(locale, 'blog.screenshot')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
