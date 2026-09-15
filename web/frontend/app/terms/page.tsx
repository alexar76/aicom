import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'Terms of Service for AI-Factory hosted storefront and pipeline.',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen px-4 py-16 pt-24 max-w-3xl mx-auto">
      <h1 className="text-4xl font-bold text-white mb-2">Terms of Service</h1>
      <p className="text-gray-500 text-sm mb-10">Last updated: June 2026</p>

      <div className="space-y-6 text-gray-300 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold text-white mb-2">1. Service</h2>
          <p>
            AI-Factory provides a self-hosted software pipeline, admin console, and optional public
            storefront. Generated products, sandbox previews, and marketplace capabilities are offered
            as-is at the time they pass automated quality gates.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">2. Accounts &amp; access</h2>
          <p>
            Admin access is restricted to operators you authorize. Demo and sandbox modes may use
            shared credentials or rate limits. You are responsible for securing your deployment,
            secrets, and LLM provider keys.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">3. Payments</h2>
          <p>
            Crypto checkout settles on-chain to addresses configured by the operator. Storefront prices
            are authoritative; we do not guarantee chain confirmation times or exchange rates.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">4. Generated content</h2>
          <p>
            LLM-generated code, copy, and designs may contain errors. You must review outputs before
            production use and remain responsible for compliance.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">5. Marketplace capabilities</h2>
          <p>
            Federated capabilities (oracles, plugins) are provided by third-party publishers. Invoke
            pricing and uptime are governed by each capability manifest and the AIMarket protocol.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">6. Limitation of liability</h2>
          <p>
            To the maximum extent permitted by law, AI-Factory and its contributors are not liable for
            indirect or consequential damages arising from use of the software on your deployment.
          </p>
        </section>
      </div>

      <p className="mt-10 text-center">
        <Link href="/privacy" className="text-sm text-indigo-300 hover:text-indigo-200 mr-4">
          Privacy Policy
        </Link>
        <Link href="/" className="text-sm text-gray-500 hover:text-white transition-colors">
          ← Back to home
        </Link>
      </p>
    </div>
  );
}
