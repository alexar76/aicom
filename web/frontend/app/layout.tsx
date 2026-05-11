import type { Metadata } from 'next';
import { Suspense } from 'react';
import '@/styles/globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { MarketingShell } from '@/components/MarketingShell';
import { GoogleAnalytics } from '@/components/GoogleAnalytics';

const site =
  (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');

export const metadata: Metadata = {
  metadataBase: new URL(site),
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="cyber-grid min-h-screen">
        <GoogleAnalytics />
        <ThemeProvider>
          <Suspense fallback={null}>
            <MarketingShell>
              <div className="relative z-10">{children}</div>
            </MarketingShell>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
