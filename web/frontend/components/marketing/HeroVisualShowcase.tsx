'use client';

import { useState } from 'react';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { ExternalLink, Play } from 'lucide-react';

const LANDING_SHOTS = [
  { src: '/gallery/landing-01.webp', alt: 'Generated landing example 1' },
  { src: '/gallery/landing-02.webp', alt: 'Generated landing example 2' },
  { src: '/gallery/landing-03.webp', alt: 'Generated landing example 3' },
];

/** Default marketing hero — https://youtu.be/Gg9a52-ZbNA */
const YOUTUBE_VIDEO_ID =
  (process.env.NEXT_PUBLIC_MARKETING_YOUTUBE_VIDEO_ID || 'Gg9a52-ZbNA').trim() || 'Gg9a52-ZbNA';

const YOUTUBE_WATCH_URL = `https://www.youtube.com/watch?v=${YOUTUBE_VIDEO_ID}`;
const YOUTUBE_EMBED_URL = `https://www.youtube-nocookie.com/embed/${YOUTUBE_VIDEO_ID}?rel=0&modestbranding=1`;
const YOUTUBE_THUMB = `https://img.youtube.com/vi/${YOUTUBE_VIDEO_ID}/hqdefault.jpg`;

type Props = {
  eyebrow: string;
  title: string;
  caption: string;
  watchLabel: string;
};

export function HeroVisualShowcase({ eyebrow, title, caption, watchLabel }: Props) {
  const [embedActive, setEmbedActive] = useState(false);

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
        <motion.div className="absolute inset-0 bg-gradient-to-br from-indigo-600/10 via-transparent to-fuchsia-600/10 pointer-events-none" />
        <div className="grid lg:grid-cols-[1.15fr_0.85fr] gap-0">
          <motion.div
            className="relative aspect-video lg:aspect-[16/10] bg-black/60 border-b lg:border-b-0 lg:border-r border-white/10"
            whileHover={{ scale: 1.005 }}
            transition={{ type: 'spring', stiffness: 260, damping: 24 }}
          >
            {embedActive ? (
              <iframe
                className="absolute inset-0 h-full w-full"
                src={`${YOUTUBE_EMBED_URL}&autoplay=1`}
                title="AI-Factory on YouTube"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
            ) : (
              <button
                type="button"
                onClick={() => setEmbedActive(true)}
                className="absolute inset-0 w-full h-full group"
                aria-label={watchLabel}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={YOUTUBE_THUMB}
                  alt=""
                  className="absolute inset-0 h-full w-full object-cover opacity-90 group-hover:opacity-100 transition"
                />
                <span className="absolute inset-0 bg-black/35 group-hover:bg-black/25 transition" />
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-full bg-red-600/95 shadow-lg shadow-red-900/40 group-hover:scale-105 transition">
                    <Play className="h-7 w-7 fill-white text-white ml-0.5" />
                  </span>
                </span>
              </button>
            )}
            <a
              href={YOUTUBE_WATCH_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full bg-black/70 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-sm border border-white/15 hover:bg-black/85 transition"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              YouTube
            </a>
          </motion.div>

          <motion.div className="grid grid-cols-3 lg:grid-cols-1 lg:grid-rows-3 gap-px bg-white/10">
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
          </motion.div>
        </div>
      </motion.div>

      <p className="text-center text-xs text-gray-500 mt-3 max-w-xl mx-auto leading-relaxed">
        {caption}{' '}
        <a
          href={YOUTUBE_WATCH_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-indigo-300/90 hover:text-indigo-200 underline underline-offset-2"
        >
          {watchLabel}
        </a>
      </p>
    </motion.div>
  );
}
