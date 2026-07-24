import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy Policy for AI-Factory storefront, admin, and lead forms.',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-3xl mx-auto">
      <h1 className="text-4xl font-bold text-white mb-2">Privacy Policy</h1>
      <p className="text-gray-500 text-sm mb-10">Last updated: June 2026</p>

      <div className="space-y-6 text-gray-300 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold text-white mb-2">What we collect</h2>
          <p>
            The platform may store product ideas submitted via public forms, admin actions, pipeline
            telemetry, and append-only marketing logs (page views, CTA clicks) on the server you
            operate. LLM prompts and responses are written to local disk for debugging and cost
            accounting unless you disable logging.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">What we do not do</h2>
          <p>
            We do not sell visitor data to ad networks. Self-hosted deployments control retention;
            delete <code className="text-indigo-300">data/</code> or rotate logs on your schedule.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">Crypto payments</h2>
          <p>
            On-chain payments expose wallet addresses and transaction hashes publicly on the
            blockchain. Payment verification reads chain data via RPC providers you configure — not
            through a centralized payment processor.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">Analytics</h2>
          <p>
            Optional Google Analytics (via <code className="text-indigo-300">NEXT_PUBLIC_GA_MEASUREMENT_ID</code>)
            may be enabled by the operator. Disable it by leaving that variable unset.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">Your rights</h2>
          <p>
            For GDPR or similar requests on a public deployment, contact the site operator via the
            lead form. Self-hosted operators are the data controller for their instance.
          </p>
        </section>
      </div>

      <p className="mt-10 text-center">
        <Link href="/terms" className="text-sm text-indigo-300 hover:text-indigo-200 mr-4">
          Terms of Service
        </Link>
        <Link href="/" className="text-sm text-gray-500 hover:text-white transition-colors">
          ← Back to home
        </Link>
      </p>
    </div>
  );
}
