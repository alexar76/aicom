'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { captureReferralFromUrl } from '@/lib/referral';
import { trackEvent } from '@/lib/analytics';
import { SupportWidget } from '@/components/SupportWidget';

export function MarketingShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    captureReferralFromUrl();
  }, []);

  useEffect(() => {
    trackEvent('page_view', { pathname });
  }, [pathname]);

  return (
    <>
      {children}
      <SupportWidget />
    </>
  );
}
