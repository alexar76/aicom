'use client';

import React from 'react';
import { cn } from '@/lib/utils';

/** Horizontal scroll wrapper for wide tables and toolbars — avoids layout blowout on narrow viewports. */
export function AdminScrollArea({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'min-w-0 overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]',
        className,
      )}
    >
      {children}
    </div>
  );
}
