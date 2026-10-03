import { useEffect, useState } from 'react';

export type VisibleViewport = { keyboardInset: number; height: number };

/**
 * The part of the screen the user can actually see while an on-screen keyboard is open.
 *
 * iOS Safari and Android Chrome (default `interactive-widget=resizes-visual`) draw the keyboard
 * OVER the page without shrinking the layout viewport, so `position: fixed; bottom: …` panels
 * keep their input under it. Returns null while no keyboard is open (or the API is missing).
 */
export function useVisibleViewport(enabled = true): VisibleViewport | null {
  const [state, setState] = useState<VisibleViewport | null>(null);

  useEffect(() => {
    const vv = typeof window !== 'undefined' ? window.visualViewport : null;
    if (!enabled || !vv) {
      setState(null);
      return undefined;
    }
    const update = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - Math.max(0, vv.offsetTop));
      setState(inset > 80 ? { keyboardInset: Math.round(inset), height: Math.round(vv.height) } : null);
    };
    update();
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    return () => {
      vv.removeEventListener('resize', update);
      vv.removeEventListener('scroll', update);
    };
  }, [enabled]);

  return state;
}
