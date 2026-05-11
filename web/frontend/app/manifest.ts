import type { MetadataRoute } from 'next';

const site =
  (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:9080').replace(/\/$/, '');

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: `${site}/`,
    name: 'AI-Factory',
    short_name: 'AI-Factory',
    description:
      'Landing generator and autonomous pipeline — storefront, sandbox preview, optional checkout.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    display_override: ['standalone', 'minimal-ui', 'browser'],
    orientation: 'any',
    background_color: '#0a0a1a',
    theme_color: '#0f172a',
    categories: ['productivity', 'developer', 'business'],
    icons: [
      {
        src: '/icon',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icon',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
