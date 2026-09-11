'use client';

import { useEffect, useLayoutEffect } from 'react';
import { applyTheme, STOREFRONT_THEME_FALLBACK } from '@/lib/utils';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * ThemeProvider — client component that loads the active theme on mount
 * and applies CSS variables globally via applyTheme().
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useLayoutEffect(() => {
    applyTheme(STOREFRONT_THEME_FALLBACK);
  }, []);

  useEffect(() => {
    const loadTheme = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/config/theme`);
        if (!res.ok) return;
        const data = await res.json();
        if (data?.theme) {
          applyTheme(data.theme);
        }
      } catch {
        /* keep STOREFRONT_THEME_FALLBACK from useLayoutEffect */
      }
    };
    loadTheme();
  }, []);

  return <>{children}</>;
}
