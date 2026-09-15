import type { Metadata } from 'next';
import Link from 'next/link';
import { Cpu, Shield, Zap, ArrowRight } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';

export const metadata: Metadata = {
  title: 'About',
  description:
    'Same multi-agent pipeline for autonomous discovery (market research, ideas) and on-demand work driven by your brief — spec through storefront.',
  openGraph: {
    title: 'About AI-Factory',
    description: 'One pipeline: autonomous or brief-led builds to share-ready software.',
    type: 'website',
  },
};

export default function AboutPage() {
  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-3xl mx-auto">
      <h1 className="text-4xl font-bold text-white mb-2">About AI-Factory</h1>
      <p className="text-gray-400 mb-10">
        Production-oriented stack for building and operating software products with LLM agents.
      </p>

      <div className="space-y-6">
        <GlassCard>
          <div className="flex items-center gap-3 mb-3">
            <Zap className="w-6 h-6 text-amber-400" />
            <h2 className="text-lg font-semibold text-white">What it does</h2>
          </div>
          <p className="text-gray-300 text-sm leading-relaxed">
            The platform coordinates the same specialized agents (product, architecture, development, QA,
            security, and more) whether the starting signal is autonomous market research and generated ideas
            or a phrase you submit — one idea moves through specification, implementation, testing, and
            go-to-market content without manual handoffs at every step. For web pages, architecture includes a
            structured <span className="text-indigo-300">ui_experience</span> brief (design tokens, typography, motion)
            so the build reads as intentional product design, not a generic template.
          </p>
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-3 mb-3">
            <Cpu className="w-6 h-6 text-indigo-400" />
            <h2 className="text-lg font-semibold text-white">How you use it</h2>
          </div>
          <p className="text-gray-300 text-sm leading-relaxed mb-4">
            Operators use the admin console to monitor the pipeline, tune LLM providers, and approve
            high-stakes steps. Visitors use the public storefront to browse products, open sandboxes,
            and purchase with crypto when a product is offered for sale.
          </p>
          <Link
            href="/lead"
            className="inline-flex items-center gap-1 text-sm text-indigo-300 hover:text-indigo-200"
          >
            Submit a product idea <ArrowRight className="w-4 h-4" />
          </Link>
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-3 mb-3">
            <Shield className="w-6 h-6 text-emerald-400" />
            <h2 className="text-lg font-semibold text-white">Trust & data</h2>
          </div>
          <p className="text-gray-300 text-sm leading-relaxed">
            Security scanning and reports are part of the workflow. Marketing analytics and lead forms
            write append-only logs on the server for operational follow-up — not ad-network resale.
          </p>
        </GlassCard>
      </div>

      <p className="mt-10 text-center">
        <Link href="/" className="text-sm text-gray-500 hover:text-white transition-colors">
          ← Back to home
        </Link>
      </p>
    </div>
  );
}
