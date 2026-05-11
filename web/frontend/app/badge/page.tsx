const embedSnippet = `<script defer src="https://aifactory.dev/ai-factory-badge.js" data-position="bottom-right"></script>`;

export const metadata = {
  title: 'Embeddable Badge',
  description: 'Add a Powered by AI-Factory badge to any site with one script tag.',
};

export default function BadgePage() {
  return (
    <main className="min-h-screen max-w-4xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-white mb-3">Embeddable Badge</h1>
      <p className="text-gray-400 mb-8">
        Add a <strong>Powered by AI-Factory</strong> badge to your product pages.
      </p>
      <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
        <h2 className="text-xl text-white font-semibold mb-3">Copy snippet</h2>
        <pre className="text-xs text-cyan-300 bg-black/30 p-4 rounded-xl overflow-auto">{embedSnippet}</pre>
        <p className="text-sm text-gray-400 mt-3">
          Optional: set <code>data-position</code> to <code>bottom-right</code> or <code>bottom-left</code>.
        </p>
      </div>
    </main>
  );
}
