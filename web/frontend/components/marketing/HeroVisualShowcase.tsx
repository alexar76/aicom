'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { Play } from 'lucide-react';

const LANDING_SHOTS = [
  { src: '/gallery/landing-01.webp', alt: 'Generated landing example 1' },
  { src: '/gallery/landing-02.webp', alt: 'Generated landing example 2' },
  { src: '/gallery/landing-03.webp', alt: 'Generated landing example 3' },
];

type Props = {
  eyebrow: string;
  title: string;
  caption: string;
  watchLabel: string;
};

export function HeroVisualShowcase({ eyebrow, title, caption, watchLabel }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoSrc, setVideoSrc] = useState('/demo/pipeline-demo.mp4');
  const [poster, setPoster] = useState('/demo/hero-preview.gif');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/public/pipeline-demo-replay', { method: 'HEAD' });
        if (!cancelled && res.ok) {
          const ct = res.headers.get('content-type') || '';
          if (ct.startsWith('video/')) {
            setVideoSrc('/api/public/pipeline-demo-replay');
          }
        }
      } catch {
        /* static fallback */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const playVideo = () => {
    const el = videoRef.current;
    if (!el) return;
    void el.play().catch(() => {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="mb-10 md:mb-12"
    >
      <p className="text-center text-[11px] md:text-xs font-semibold uppercase tracking-[0.22em] text-indigo-300/90 mb-2">
        {eyebrow}
      </p>
      <h2 className="text-center text-xl md:text-2xl font-bold text-white mb-5 max-w-2xl mx-auto leading-snug">
        {title}
      </h2>

      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.55, delay: 0.05 }}
        className="relative rounded-2xl border border-white/15 bg-black/40 shadow-[0_0_80px_-20px_rgba(99,102,241,0.55)] overflow-hidden ring-1 ring-indigo-500/25"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-600/10 via-transparent to-fuchsia-600/10 pointer-events-none" />
        <div className="grid lg:grid-cols-[1.15fr_0.85fr] gap-0">
          <motion.div
            className="relative aspect-video lg:aspect-[16/10] bg-black/60 border-b lg:border-b-0 lg:border-r border-white/10"
            whileHover={{ scale: 1.005 }}
            transition={{ type: 'spring', stiffness: 260, damping: 24 }}
          >
            <video
              ref={videoRef}
              className="absolute inset-0 h-full w-full object-cover"
              src={videoSrc}
              poster={poster}
              controls
              playsInline
              muted
              preload="metadata"
            />
            <button
              type="button"
              onClick={playVideo}
              className="absolute bottom-3 left-3 inline-flex items-center gap-2 rounded-full bg-black/70 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-sm border border-white/15 hover:bg-black/85 transition"
              aria-label={watchLabel}
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              {watchLabel}
            </button>
          </motion.div>

          <div className="grid grid-cols-3 lg:grid-cols-1 lg:grid-rows-3 gap-px bg-white/10">
            {LANDING_SHOTS.map((shot, i) => (
              <motion.div
                key={shot.src}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.12 + i * 0.06 }}
                className="relative aspect-[4/3] lg:aspect-auto lg:flex-1 min-h-[72px] bg-gray-950"
              >
                <Image
                  src={shot.src}
                  alt={shot.alt}
                  fill
                  className="object-cover object-top"
                  sizes="(max-width: 1024px) 33vw, 280px"
                  priority={i === 0}
                />
              </motion.div>
            ))}
          </div>
        </div>
      </motion.div>

      <p className="text-center text-xs text-gray-500 mt-3 max-w-xl mx-auto leading-relaxed">{caption}</p>
    </motion.div>
  );
}
