'use client';

import { useEffect } from 'react';
import { applyTheme } from '@/lib/utils';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * ThemeProvider — client component that loads the active theme on mount
 * and applies CSS variables globally via applyTheme().
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
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
        // Theme loading is non-critical; use defaults from CSS
      }
    };
    loadTheme();
  }, []);

  return <>{children}</>;
}
