'use client';

import { useState } from 'react';
import { ArrowUpRight, Sparkles } from 'lucide-react';
import { ProductNavLink } from './ProductNavLink';
import { useStorefrontCatalog } from '@/hooks/useStorefrontCatalog';
import { productReviewState } from '@/lib/productReviewState';
import { getMarketingStrings } from '@/lib/marketing';
import type { SiteLocale } from '@/lib/siteLocale';
import { visitorJourney, generatorPath, localePath } from '@/lib/visitorJourney';

const action = 'inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 py-3 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300';
export function VisitorStart({ locale }: { locale: SiteLocale }) {
  const c = visitorJourney[locale];
  return <section id="hero-generate" className="relative px-4 py-12 sm:py-20 scroll-mt-40">
    <div className="mx-auto max-w-4xl rounded-3xl border border-fuchsia-400/25 bg-gradient-to-br from-fuchsia-950/50 to-indigo-950/40 p-6 sm:p-12">
      <p className="mb-4 text-xs font-semibold tracking-[0.2em] text-fuchsia-300">AICOM / FACTORY</p>
      <h1 className="text-4xl font-bold text-white sm:text-6xl">{c.title}</h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-gray-300">{c.intro}</p>
      <ol className="my-7 flex flex-col gap-3 text-sm text-gray-300 sm:flex-row sm:flex-wrap sm:gap-6">{c.steps.map((step, index) => <li key={step}><span className="mr-2 text-fuchsia-300">0{index + 1}</span>{step}</li>)}</ol>
      <div className="flex flex-wrap gap-3">
        <a href={generatorPath(locale)} className={`${action} bg-fuchsia-600 text-white hover:bg-fuchsia-500`}><Sparkles size={18}/>{c.start}</a>
        <a href="#products" className={`${action} border border-white/20 text-gray-200 hover:bg-white/10`}>{c.examples}</a>
      </div>
      <p className="mt-4 text-sm text-cyan-300"><a href={generatorPath(locale)} className="inline-flex min-h-10 items-center hover:underline">{c.assistantGenerator} →</a></p>
      <div className="mt-8 border-t border-white/10 pt-5 text-sm text-gray-400"><a href="/admin" className="inline-flex items-center gap-1 text-cyan-300 hover:underline">{c.demo}<ArrowUpRight size={16}/></a><p className="mt-2 max-w-2xl leading-relaxed">{c.demoNote}</p><a href="#factory-build" className="mt-2 mr-5 inline-flex min-h-10 items-center text-cyan-300 hover:underline">{c.pipelineBuild} →</a><a href="/docs" className="mt-2 inline-flex min-h-10 items-center text-cyan-300 hover:underline">{getMarketingStrings(locale).navDocs} →</a></div>
    </div>
  </section>;
}

export function VisitorCatalog({ locale }: { locale: SiteLocale }) {
  const c = visitorJourney[locale];
  const [query, setQuery] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [category, setCategory] = useState('all');
  const { products, categories, loading, refreshing, error, revalidate } = useStorefrontCatalog('all');
  const filtered = products.filter(p => (category === 'all' || (p.category || 'uncategorized') === category) && (!verifiedOnly || productReviewState(p) === 'verified') &&
    [p.name, p.spec?.product_name, p.selling_description, p.idea, ...(p.tags || []), ...Object.values(p.implementation_summary || {})].some((value: string | undefined) => value?.toLowerCase().includes(query.trim().toLowerCase())))
    .sort((a, b) => Number(productReviewState(b) === 'verified') - Number(productReviewState(a) === 'verified'));
  const groups = [
    { id: 'landing-products', title: c.landings, note: c.landingsNote, items: filtered.filter(p => p.delivery_profile === 'marketing_landing') },
    { id: 'full-products', title: c.fullProducts, note: c.fullProductsNote, items: filtered.filter(p => p.delivery_profile !== 'marketing_landing') },
  ];
  const categoryIds = [...new Set(products.map(p => p.category || 'uncategorized'))];
  return <section id="products" className="scroll-mt-40 px-4 py-12">
    <div className="mx-auto max-w-6xl">
      <h2 className="text-3xl font-bold text-white sm:text-4xl">{c.catalog}</h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-gray-400">{c.catalogNote}</p>
      <nav aria-label={c.catalog} className="mt-6 grid gap-3 sm:grid-cols-2">{groups.map(group => <a key={group.id} href={`#${group.id}`} className="rounded-2xl border border-cyan-400/25 bg-cyan-950/20 p-5 hover:bg-cyan-950/40"><span className="flex items-center justify-between gap-3 text-lg font-semibold text-white">{group.title}<span className="text-cyan-300">{group.items.length} ↓</span></span><span className="mt-2 block text-sm text-gray-400">{group.note}</span></a>)}</nav>
      <div className="my-6 flex flex-wrap items-center gap-3">
        <label className="w-full sm:max-w-sm"><span className="sr-only">{c.search}</span><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder={c.search} className="w-full rounded-xl border border-white/20 bg-black/20 px-4 py-3 text-white focus:outline-cyan-300"/></label>
        {[false, true].map(only => <button type="button" key={String(only)} aria-pressed={verifiedOnly === only} onClick={() => setVerifiedOnly(only)} className={`min-h-11 rounded-xl border px-4 text-sm ${verifiedOnly === only ? 'border-cyan-400/50 bg-cyan-400/10 text-cyan-200' : 'border-white/10 text-gray-400'}`}>{only ? c.verified : c.all} <span className="ml-1 tabular-nums">({only ? products.filter(p => productReviewState(p) === 'verified').length : products.length})</span></button>)}
      </div>
      <div className="mb-5 flex flex-wrap gap-2" aria-label={c.categories}>{['all', ...categoryIds].map(id => <button key={id} type="button" aria-pressed={category === id} onClick={() => setCategory(id)} className={`min-h-11 rounded-xl border px-3 text-sm ${category === id ? 'border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-200' : 'border-white/10 text-gray-400'}`}>{id === 'all' ? c.allCategories : categories.find(cat => cat.id === id)?.name || id} ({id === 'all' ? products.length : products.filter(p => (p.category || 'uncategorized') === id).length})</button>)}</div>
      <div className="mb-6 flex flex-wrap gap-5 text-sm text-cyan-300"><a href="/builds" className="min-h-11 py-3 hover:underline">{c.replays} →</a><a href="/explore" className="min-h-11 py-3 hover:underline">{c.explore} →</a><a href="/benchmark" className="min-h-11 py-3 hover:underline">{c.benchmark} →</a></div>
      <p role="status" className="mb-3 text-sm text-gray-400">{loading || refreshing ? c.updating : `${c.results}: ${filtered.length} / ${products.length}`}</p>
      {error && products.length === 0 ? <div role="alert" className="py-8 text-gray-300"><p>{c.error}</p><button onClick={revalidate} className="mt-3 text-cyan-300 underline">{c.retry}</button></div> : null}
      {!loading && !error && filtered.length === 0 ? <div className="rounded-xl border border-white/10 p-8 text-gray-300"><p>{c.empty}</p><button className="mt-3 text-cyan-300 underline" onClick={() => { setQuery(''); setVerifiedOnly(false); setCategory('all'); }}>{c.reset}</button></div> : null}
      <div className="space-y-12">{groups.map(group => <section key={group.id} id={group.id} aria-labelledby={`${group.id}-title`} className="scroll-mt-40 border-t border-white/10 pt-8">
        <h3 id={`${group.id}-title`} className="text-2xl font-semibold text-white">{group.title} <span className="text-cyan-300">({group.items.length})</span></h3>
        <p className="mb-6 mt-2 text-sm text-gray-400">{group.note}</p>
        {!loading && !error && group.items.length === 0 && <p className="rounded-xl border border-white/10 p-5 text-gray-400">{c.empty}</p>}
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">{group.items.map(product => {
          const state = productReviewState(product);
          return <ProductNavLink key={product.id} href={`/product/${product.id}`} className="flex h-full flex-col rounded-2xl border border-white/10 bg-white/[0.035] p-6 transition hover:border-cyan-400/50 focus-visible:outline-cyan-300">
            <div className="mb-4 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-white/10 px-3 py-1 text-gray-300">{product.delivery_profile === 'marketing_landing' ? c.landing : c.software}</span><span className={`rounded-full px-3 py-1 ${state === 'verified' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-amber-500/10 text-amber-200'}`}>{c[state]}</span></div>
            <h4 className="line-clamp-2 text-xl font-semibold text-white">{product.name || product.spec?.product_name || product.idea}</h4>
            <p className="my-3 line-clamp-3 text-sm leading-relaxed text-gray-400">{product.selling_description || product.spec?.description || product.idea}</p>
            <div className="mb-3 flex flex-wrap gap-2 text-xs text-gray-400">{product.is_template && <span className="rounded bg-amber-500/10 px-2 py-1 text-amber-200">{c.template}</span>}{product.category && <span className="rounded bg-white/5 px-2 py-1">{categories.find(cat => cat.id === product.category)?.name || product.category}</span>}{(product.tags || []).slice(0, 3).map(tag => <span key={tag} className="rounded bg-white/5 px-2 py-1">{tag}</span>)}</div>
            {product.implementation_summary && <div className="mb-4 flex flex-wrap gap-2 text-xs text-gray-400">{Object.entries(product.implementation_summary).slice(0, 4).map(([key, value]) => <span key={key} title={`${key}: ${value}`} className="max-w-full truncate rounded border border-white/10 px-2 py-1">{key}: {value}</span>)}</div>}
            {product.price_usdt != null && product.price_usdt > 0 && <p className="text-sm font-semibold text-emerald-300">${product.price_usdt}{c.perMonth}</p>}
            <span className="mt-auto inline-flex items-center gap-2 pt-4 text-sm text-cyan-300">{c.details}<ArrowUpRight size={16}/></span>
          </ProductNavLink>;
        })}</div>
      </section>)}</div>
    </div>
  </section>;
}

export function VisitorNext({ locale }: { locale: SiteLocale }) {
  const c = visitorJourney[locale];
  return <>
    <section className="mx-auto max-w-6xl px-4 py-12"><h2 className="mb-6 text-2xl font-bold text-white">{c.faq}</h2><div className="grid gap-4 md:grid-cols-3">{c.questions.map(([q, a]) => <div key={q} className="rounded-xl border border-white/10 p-5"><h3 className="font-semibold text-white">{q}</h3><p className="mt-3 text-sm leading-relaxed text-gray-400">{a}</p></div>)}</div></section>
    <section className="mx-auto max-w-6xl px-4 py-12"><div className="rounded-2xl border border-cyan-400/20 bg-cyan-950/20 p-6 sm:p-10"><h2 className="max-w-3xl text-2xl font-semibold text-white">{c.next}</h2><div className="mt-6 flex flex-wrap gap-3"><a className={`${action} bg-cyan-300 text-slate-950`} href={`https://ecosystem.modelmarket.dev${localePath(locale)}`}>{c.ecosystem}<ArrowUpRight size={18}/></a><a className={`${action} border border-white/20 text-cyan-200`} href={`https://edu.modelmarket.dev${localePath(locale)}ai-pays-ai/`}>{c.lesson}<ArrowUpRight size={18}/></a></div></div></section>
  </>;
}
