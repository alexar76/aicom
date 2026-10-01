import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    lang: 'en',
    name: 'AI-Factory',
    short_name: 'AI-Factory',
    description:
      'Landing generator and autonomous pipeline — storefront, sandbox preview, optional checkout.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'any',
    background_color: '#0a0a1a',
    theme_color: '#0f172a',
    categories: ['productivity', 'developer', 'business'],
    // Static PNG sizes — Chrome/Android WebAPK often rejects a single dynamic /icon for installability.
    icons: [
      {
        src: '/icons/icon-192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
