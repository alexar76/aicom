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
      <p className="text-gray-500 text-sm mb-10">Last updated: September 2026</p>

      <div className="space-y-6 text-gray-300 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold text-white mb-2">What we collect</h2>
          <p>
            The platform may store product ideas submitted via public forms, admin actions, pipeline
            telemetry, and append-only marketing logs (page views, CTA clicks) on the server you
            operate. First-party request logs record the visitor&apos;s IP address, user-agent and the
            pages requested. LLM prompts and responses are written to local disk for debugging and
            cost accounting unless you disable logging.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">IP addresses</h2>
          <p>
            An IP address is personal data under the GDPR and personal information under US state law,
            so we minimise it. In the traffic analytics pipeline, IP addresses are{' '}
            <strong className="text-gray-100">anonymised at ingest</strong> — truncated to their
            network (IPv4 <code className="text-indigo-300">a.b.c.0</code> /24, IPv6 /48) — so an
            individual device is no longer singled out, and those records are retained for{' '}
            <strong className="text-gray-100">at most 90 days</strong>. The full address is used only
            transiently to rate-limit submissions and in short-lived security/audit logs to prevent
            abuse (a legitimate interest). Country and network are derived before truncation, so
            analytics and abuse detection keep working.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-2">What we do not do</h2>
          <p>
            We do not sell visitor data, and the storefront loads{' '}
            <strong className="text-gray-100">no Google Analytics or other third-party trackers</strong>
            {' '}— no cross-site or advertising cookies. Everything is first-party, on the host you
            operate. Self-hosted deployments control retention; delete{' '}
            <code className="text-indigo-300">data/</code> or change the log-retention window on your
            schedule.
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
          <h2 className="text-lg font-semibold text-white mb-2">Your rights</h2>
          <p>
            For GDPR, CCPA/CPRA or similar access and erasure requests on a public deployment, contact
            the site operator via the lead form. Self-hosted operators are the data controller for
            their instance. Which law applies depends on where visitors are located, not where the
            operator is incorporated.
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
