'use client';

import React, { useEffect, useState } from 'react';
import { Copy, Download, UserRound } from 'lucide-react';
import api from '@/lib/api';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';

export default function AccountPage() {
  const [orders, setOrders] = useState<any[]>([]);
  const [email, setEmail] = useState('');
  const [plan, setPlan] = useState('free');
  const [usage, setUsage] = useState<{ period_ym: string; runs_count: number } | null>(null);
  const [error, setError] = useState('');
  const [upgradeLoading, setUpgradeLoading] = useState(false);
  const [upgradeMessage, setUpgradeMessage] = useState('');
  const [referral, setReferral] = useState<null | {
    referral_code: string;
    conversions: number;
    attributed_revenue: number;
    share_link: string;
  }>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const me = await api.getCustomerMe();
        setEmail(me.email);
        setPlan((me.plan || 'free').toLowerCase());
        setUsage(me.usage || null);
        const r = await api.getMyReferralDashboard();
        setReferral(r);
        const data = await api.getCustomerOrders();
        setOrders(data.orders || []);
      } catch (err: any) {
        const msg = err?.message || '';
        if (/401|Not authenticated|customer token|Missing/i.test(msg)) {
          setError('Sign in on Checkout (email / password), then open Account again.');
        } else {
          setError(msg || 'Could not load orders.');
        }
      }
    };
    load();
  }, []);

  const startUpgrade = async (targetPlan: 'maker' | 'studio') => {
    setUpgradeLoading(true);
    setUpgradeMessage('');
    try {
      const session = await api.createStripeCheckoutSession(targetPlan);
      if (!session.checkout_url) {
        throw new Error('Stripe checkout URL missing');
      }
      window.location.href = session.checkout_url;
    } catch (err: any) {
      setUpgradeMessage(err?.message || 'Could not start Stripe checkout.');
    } finally {
      setUpgradeLoading(false);
    }
  };

  const copyShareLink = async () => {
    if (!referral?.share_link) return;
    try {
      await navigator.clipboard.writeText(referral.share_link);
      setUpgradeMessage('Referral link copied.');
    } catch {
      setUpgradeMessage('Could not copy referral link.');
    }
  };

  return (
    <main className="min-h-screen max-w-5xl mx-auto px-4 py-10">
      <h1 className="text-3xl font-bold text-white mb-6">Customer Account</h1>
      {email && (
        <div className="glass rounded-xl p-3 text-sm text-gray-300 mb-6 flex items-center gap-2">
          <UserRound className="w-4 h-4" />
          {email} • plan: {plan}
        </div>
      )}
      {usage && plan === 'free' && (
        <GlassCard className="mb-6">
          <p className="text-sm text-gray-300 mb-2">
            Free tier usage: {usage.runs_count}/3 runs in {usage.period_ym}
          </p>
          <div className="flex gap-3">
            <Button onClick={() => startUpgrade('maker')} loading={upgradeLoading}>
              Upgrade to Maker
            </Button>
            <Button variant="secondary" onClick={() => startUpgrade('studio')} loading={upgradeLoading}>
              Upgrade to Studio
            </Button>
          </div>
          {upgradeMessage && <p className="text-red-300 text-sm mt-2">{upgradeMessage}</p>}
        </GlassCard>
      )}
      {referral && (
        <GlassCard className="mb-6">
          <p className="text-sm text-gray-300 mb-2">
            Referral code: <span className="text-indigo-300 font-semibold">{referral.referral_code}</span>
          </p>
          <p className="text-sm text-gray-400 mb-3">
            Conversions: {referral.conversions} • Attributed revenue: ${referral.attributed_revenue}
          </p>
          <div className="flex gap-3 items-center">
            <a className="text-xs text-cyan-300 underline break-all" href={referral.share_link}>
              {referral.share_link}
            </a>
            <Button variant="secondary" icon={<Copy className="w-4 h-4" />} onClick={copyShareLink}>
              Copy
            </Button>
          </div>
        </GlassCard>
      )}
      {error && (
        <p className="text-red-400 mb-6">{error}</p>
      )}
      <div className="space-y-4">
        {orders.map((order) => (
          <GlassCard key={order.id}>
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-white font-medium">Order {order.id}</p>
                <p className="text-sm text-gray-400">Product: {order.product_id}</p>
                <p className="text-xs text-emerald-300">License: {order.license_key}</p>
              </div>
              <a href={`/api/customer/orders/${order.id}/download`}>
                <Button icon={<Download className="w-4 h-4" />}>Download ZIP</Button>
              </a>
            </div>
          </GlassCard>
        ))}
      </div>
    </main>
  );
}
