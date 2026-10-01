'use client';

import Link, { useLinkStatus } from 'next/link';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

function ProductLinkPendingOverlay() {
  const { pending } = useLinkStatus();
  if (!pending) return null;

  return (
    <div
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-2xl bg-black/45 backdrop-blur-[2px]"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-8 w-8 animate-spin text-indigo-400" aria-hidden />
      <span className="text-xs font-medium text-indigo-200/90">Opening…</span>
    </div>
  );
}

export function ProductNavLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className={cn('relative block', className)}>
      <ProductLinkPendingOverlay />
      {children}
    </Link>
  );
}
