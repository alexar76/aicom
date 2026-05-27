'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  onClick?: () => void;
  id?: string;
}

export function GlassCard({
  children,
  className,
  hover = true,
  glow = false,
  onClick,
  id,
}: GlassCardProps) {
  return (
    <motion.div
      id={id}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className={cn(
        'glass-card p-6',
        hover && 'cursor-pointer',
        glow && 'neon-border',
        className
      )}
      whileHover={hover ? { y: -4, transition: { duration: 0.2 } } : undefined}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}
