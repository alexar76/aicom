import type { Metadata, Viewport } from 'next';
import { Suspense } from 'react';
import '@/styles/globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { MarketingShell } from '@/components/MarketingShell';
import { AiMarketWidgetLoader } from '@/components/AiMarketWidgetLoader';
import { GoogleAnalytics } from '@/components/GoogleAnalytics';
import { PwaRegister } from '@/components/PwaRegister';

const site =
  (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:9080').replace(/\/$/, '');

export const metadata: Metadata = {
  metadataBase: new URL(site),
  applicationName: 'AI-Factory',
  title: {
    default: 'AI-Factory — Generate landings from one phrase',
    template: '%s — AI-Factory',
  },
  description:
    'AI-built landing pages: type a phrase, run the pipeline, preview in sandbox. Same multi-agent stack behind every page — quality gates, optional crypto checkout.',
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
      'Landing generator first — phrase to HTML/CSS page. Full pipeline, sandbox preview, optional checkout.',
    type: 'website',
    url: site,
    siteName: 'AI-Factory',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI-Factory',
    description: 'One brief → share-ready page; quality gates included.',
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
    <html lang="en" className="dark" data-theme-bg="dark">
      <head>
        <link rel="stylesheet" href="/themes.css" />
      </head>
      <body className="cyber-grid min-h-screen min-w-0 overflow-x-hidden antialiased">
        <PwaRegister />
        <GoogleAnalytics />
        <ThemeProvider>
          <Suspense fallback={null}>
            <MarketingShell>
              <div className="relative z-10 min-w-0">{children}</div>
              <AiMarketWidgetLoader />
            </MarketingShell>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
