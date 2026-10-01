'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Lightbulb, Send, Loader2, CheckCircle2, ExternalLink } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { submitLead, trackEvent } from '@/lib/analytics';

export default function LeadPage() {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [idea, setIdea] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [statusUrl, setStatusUrl] = useState('');
  const [pipelineStarted, setPipelineStarted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (idea.trim().length < 10) {
      setError('Please describe your idea in at least a few sentences.');
      return;
    }
    setLoading(true);
    try {
      const res = await submitLead({ email, idea, name: name || undefined, company: company || undefined });
      trackEvent('lead_submit', { source: 'lead_page', pipeline: res.pipeline_started });
      setStatusUrl(res.status_url || '');
      setPipelineStarted(Boolean(res.pipeline_started));
      setDone(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Lightbulb className="w-8 h-8 text-amber-400" />
        <h1 className="text-3xl font-bold text-white">Idea → pipeline</h1>
      </div>
      <p className="text-gray-400 mb-8 text-sm">
        Submit your brief — we start the factory pipeline automatically and email you when it&apos;s ready.
      </p>

      {done ? (
        <GlassCard className="text-center py-10">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-4" />
          <p className="text-white font-medium mb-2">
            {pipelineStarted ? 'Pipeline started' : 'Received'}
          </p>
          <p className="text-gray-400 text-sm mb-6">
            {pipelineStarted
              ? 'Track build progress on your status page. We email you when the product ships.'
              : 'Thanks — your idea was saved.'}
          </p>
          {statusUrl && (
            <Link
              href={statusUrl}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm mb-4"
            >
              Track status
              <ExternalLink className="w-4 h-4" />
            </Link>
          )}
          <div>
            <Link href="/" className="text-sm text-indigo-300 hover:text-indigo-200">
              Back to home
            </Link>
          </div>
        </GlassCard>
      ) : (
        <GlassCard>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Email *</label>
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full"
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Company</label>
                <Input
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Optional"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Your idea *</label>
              <textarea
                required
                minLength={10}
                rows={6}
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                placeholder="Problem, audience, must-have features, constraints..."
              />
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button type="submit" loading={loading} icon={<Send className="w-4 h-4" />}>
              Start pipeline
            </Button>
          </form>
        </GlassCard>
      )}
    </div>
  );
}
