'use client';

import { Loader2 } from 'lucide-react';
import { t, type AdminLocale } from '@/lib/adminI18n';

export function AdminAuthGate({
  locale,
  label,
}: {
  locale: AdminLocale;
  label?: string;
}) {
  return (
    <div
      className="flex min-h-[100dvh] flex-col items-center justify-center bg-[#0a0a0f] px-4 text-gray-400"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Loader2 className="mb-4 h-10 w-10 animate-spin text-indigo-400" aria-hidden />
      <p className="text-sm">{label ?? t(locale, 'app.authChecking')}</p>
    </div>
  );
}
