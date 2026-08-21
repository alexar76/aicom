'use client';

import { useEffect } from 'react';

/**
 * Registers the app shell service worker in production so browsers allow
 * “Install app” / Add to Home Screen where criteria require a SW.
 */
export function PwaRegister() {
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return;
    if (process.env.NODE_ENV !== 'production') return;

    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
      /* ignore — HTTP offline or blocked */
    });
  }, []);

  return null;
}
