export const metadata = {
  title: 'Launch Kit',
  description: 'Press kit, launch checklist, and distribution starter pack for AI-Factory releases.',
};

const checklist = [
  'Finalize homepage and benchmark screenshots.',
  'Record demo video: "10 products in 2 minutes".',
  'Prepare Product Hunt tagline, first comment, and maker profile copy.',
  'Prepare Show HN post with architecture + live metrics.',
  'Prepare Reddit/IndieHackers posts with UTM links.',
  'Validate Stripe checkout and free-tier upgrade prompts.',
  'Publish changelog and support contact channels.',
];

export default function LaunchKitPage() {
  return (
    <main className="min-h-screen max-w-5xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-white mb-3">Launch Kit</h1>
      <p className="text-gray-400 mb-8">
        One place for Product Hunt, Show HN, and community launch assets.
      </p>
      <section className="rounded-2xl border border-white/10 bg-white/5 p-6 mb-6">
        <h2 className="text-2xl text-white font-semibold mb-3">Press Kit</h2>
        <ul className="space-y-2 text-gray-200">
          <li>- Product name: AI-Factory</li>
          <li>- Tagline: One phrase to launch-ready product assets.</li>
          <li>- Core proof: benchmark pass rates + live trust block metrics.</li>
          <li>- Assets: logo, product screenshots, benchmark page captures, and short demo clips.</li>
        </ul>
      </section>
      <section className="rounded-2xl border border-white/10 bg-white/5 p-6">
        <h2 className="text-2xl text-white font-semibold mb-3">Launch Checklist</h2>
        <ul className="space-y-2 text-gray-200">
          {checklist.map((item) => (
            <li key={item}>- {item}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
