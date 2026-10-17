import type { Metadata, Viewport } from 'next';
import { Suspense } from 'react';
import '@/styles/globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { MarketingShell } from '@/components/MarketingShell';
import { AiMarketWidgetLoader } from '@/components/AiMarketWidgetLoader';
import { PwaRegister } from '@/components/PwaRegister';
import { isFactoryLanding } from '@/lib/siteRole';

const site =
  (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:9080').replace(/\/$/, '');

export const metadata: Metadata = {
  metadataBase: new URL(site),
  applicationName: 'AI-Factory',
  title: {
    default: 'AI-Factory — Create, preview, explore',
    template: '%s — AI-Factory',
  },
  description:
    'Create a landing page, preview and download it. Explore factory builds, their review status, and the open agent economy.',
  keywords: [
    'AI',
    'landing page',
    'campaign page',
    'AI factory',
    'LLM',
    'pipeline',
    'autonomous',
    'software development',
  ],
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'AI-Factory',
  },
  openGraph: {
    title: 'AI-Factory',
    description:
      'Describe an idea, preview your landing page and download its files. Explore the autonomous factory and agent economy.',
    type: 'website',
    url: site,
    siteName: 'AI-Factory',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI-Factory',
    description: 'One brief → landing preview and files. Explore what the factory can build.',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0f172a' },
    { media: '(prefers-color-scheme: light)', color: '#f8fafc' },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning covers this element's own attributes only: pages whose body the
    // server rendered in the visitor's language set `lang` before hydration (DocumentLang).
    <html lang="en" data-scroll-behavior="smooth" className="dark" data-theme-bg="dark" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line @next/next/no-css-tags -- self-hosted webfonts in /public/fonts (scripts/selfhost_google_fonts.py); a CSS @import of this URL fails the Turbopack build */}
        <link rel="stylesheet" href="/fonts/fonts.css" />
        {/* eslint-disable-next-line @next/next/no-css-tags -- runtime-swappable theme stylesheet served from /public, intentionally loaded by URL */}
        <link rel="stylesheet" href="/themes.css" />
      </head>
      <body className="cyber-grid min-h-screen min-w-0 overflow-x-hidden antialiased">
        {!isFactoryLanding() && <PwaRegister />}
        <ThemeProvider>
          <Suspense fallback={null}>
            <MarketingShell>
              <div className="relative z-10 min-w-0">{children}</div>
              {!isFactoryLanding() && <AiMarketWidgetLoader />}
            </MarketingShell>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
