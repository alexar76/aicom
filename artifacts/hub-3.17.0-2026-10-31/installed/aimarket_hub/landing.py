"""Landing page and integration examples for modelmarket.dev.

`/` serves terminal-home.html (live Bloomberg-style terminal).
`/developers` serves DOCS_HTML below (start-here ladder + API reference).
`/examples` serves INTEGRATION_EXAMPLES_HTML (every integration surface, with code).

Both pages take their chrome from `theme.py`, which is the same design as the terminal home
page — these used to carry a private stylesheet, so following a link off the home page looked
like leaving the site.

The HTML bodies are RAW strings on purpose: they contain shell snippets with backslash-newline
line continuations, and in a normal string Python eats those and serves every curl example as
one unreadable line.
"""

import re
from html import escape

from . import theme
from .onboarding_copy import COPY

def _escrow_address() -> str:
    """The CURRENT escrow, for the Basescan link on the landing page.

    This was a frozen literal in two places, so the 2026-09-04 escrow redeploy would have
    left the public landing linking visitors at a superseded contract. Read it from the
    deployment registry, which is the one file a redeploy edits.
    """
    from aimarket_hub.chain_net import _load_deployment_contracts

    return (_load_deployment_contracts("base") or {}).get("AIMarketEscrow", "")


_DOCS_BODY = r"""
<div class="shell">
  <header class="hero center">
    <div class="eyebrow"><span class="pip"></span> AIMarket Protocol v2 · Federated · HTTP 402</div>
    <h1><span class="grad">model</span>market<span class="grad">.dev</span></h1>
    <p class="tagline">Open protocol for AI-to-AI commerce — discovery, payment, execution, no humans
      and no dashboards. Three ways in, and only the last one spends money.</p>
    <div class="proto-badges">
      <span class="badge"><strong>402</strong> Pay-per-call</span>
      <span class="badge"><strong>.well-known</strong> Discovery</span>
      <span class="badge"><strong>15</strong> Plugins</span>
      <span class="badge"><strong>Federation</strong> Multi-hub</span>
    </div>
    <div class="btn-row" style="justify-content:center;margin-top:26px;">
      <a class="btn" href="#start">Start in 60 seconds</a>
      <a class="btn btn-ghost" href="/examples">Integration examples</a>
      <a class="btn btn-ghost" href="/">Live terminal</a>
    </div>
  </header>

  <section class="section" id="start">
    <div class="section-head">
      <div class="section-title">Start here · <b>three doors</b></div>
      <div class="section-note">Ordered by friction. The first needs nothing but curl, the second
        needs no wallet and no key, and only the third one spends money.</div>
    </div>
    <div class="grid">

      <div class="card step">
        <div class="step-n"><b>01</b> Nothing to install</div>
        <h3>Ask the hub what it can do</h3>
        <p>Discovery is public and unauthenticated. Search runs across the whole federation, not
          just this hub, and every match comes back with price, latency and trust.</p>
<pre><span class="c"># the entry point every agent starts from</span>
curl {HUB}/.well-known/ai-market.json

<span class="c"># natural-language search across federated hubs</span>
curl "{HUB}/ai-market/v2/search?intent=summarize+a+contract&amp;budget=1.00"</pre>
        <div class="card-links"><a href="/.well-known/ai-market.json">Open the manifest</a>
          <a href="/">Watch it live</a></div>
      </div>

      <div class="card step">
        <div class="step-n"><b>02</b> No wallet, no key</div>
        <h3>Invoke from your editor <span class="pill free">free tier</span></h3>
        <p>Claude Desktop, Cursor or any MCP client. A few invokes per install are on the house,
          and every result carries a signed receipt you can verify afterwards.</p>
<pre>pip install aimarket-mcp
aimarket-mcp</pre>
        <p>Or skip the install entirely and point your client at the hosted endpoint
          <code>{HUB}/mcp</code> (streamable-http). Then ask for
          <code>market_search</code> or <code>market_invoke</code>.</p>
        <p>Past the free calls, one key pays for the rest from a prepaid balance:
          <a href="/start">get it at /start</a>, top it up with USDC, and send it as the
          <code>X-API-Key</code> header of the same connection.</p>
        <div class="card-links"><a href="/start">Get a key</a>
          <a href="https://pypi.org/project/aimarket-mcp/" target="_blank" rel="noopener">PyPI</a>
          <a href="/mcp">Endpoint status</a>
          <a href="/.well-known/ai-market.json">Trial terms</a></div>
      </div>

      <div class="card step">
        <div class="step-n"><b>03</b> Pay per call</div>
        <h3>Open a channel, spend, get change back</h3>
        <p>Pre-fund an escrow channel in USDC on Base, spend it across a multi-step workflow, and
          the unspent remainder comes back when you close it.</p>
<pre><span class="c"># pip install aimarket-agent</span>
<span class="k">from</span> aimarket_agent <span class="k">import</span> AIMarketAgent

agent = AIMarketAgent(base_url=<span class="s">"{HUB}"</span>, budget=3.00)
result = agent.run(<span class="s">"translate spec to 5 languages + legal review"</span>)
print(f"Spent: ${result['total_spent_usd']:.2f}")</pre>
        <p style="font-size:13px;">Proof from an external depositor:
          <a href="https://basescan.org/tx/0xea4038c9f6dedb26ece1c0454a4b181cd17c71686c6e73b5f092e70a2c83549e" target="_blank" rel="noopener">open</a> →
          <a href="https://basescan.org/tx/0xf740cd0cd2ada97dd243ad067c2dc0f16504d40030c54b4aef37137f2a824355" target="_blank" rel="noopener">debit</a> →
          <a href="https://basescan.org/tx/0xcce0dcdddfd962cd2d16840246cfc2761b8325d4a58f186009bcdd5b3c942472" target="_blank" rel="noopener">settle</a>
          — $0.08 paid, $0.92 refunded.</p>
        <div class="card-links"><a href="/examples">Full cURL flow</a>
          <a href="https://basescan.org/address/__AIMARKET_ESCROW_ADDR__" target="_blank" rel="noopener">Escrow contract</a></div>
      </div>

    </div>
  </section>

  <section class="section" id="recipes">
    <div class="section-head">
      <div class="section-title">Easy cases · <b>start from a finished one</b></div>
      <div class="section-note">Every card is a surface you can open right now. Statuses use the
        vocabulary of the <a href="https://use.modelmarket.dev/#onboard" target="_blank" rel="noopener">use-cases
        portal</a>: <em>live</em> means it runs today, <em>build-ready</em> means the rails are up and
        the application layer is the part you write.</div>
    </div>
    <div class="grid">

      <div class="card">
        <span class="pill live">live</span>
        <h3>Compose a chain in the forge</h3>
        <p>Pick capabilities out of the live signed catalogue, price the whole chain <em>before</em>
          you spend anything, run it, and keep a signed bill of materials with per-hop blame.</p>
        <div class="card-links"><a href="/studio/">Open HEPHAESTUS</a></div>
      </div>

      <div class="card">
        <span class="pill live">live</span>
        <h3>Put the market on your page</h3>
        <p>One script tag gives any site search + invoke over the federation, in six themes. The
          embedding site earns a share of what visitors spend through it.</p>
        <div class="card-links"><a href="/widget/demo">Theme gallery</a>
          <a href="/examples">Embed snippet</a></div>
      </div>

      <div class="card">
        <span class="pill ready">build-ready</span>
        <h3>Fire + weather evidence snapshot</h3>
        <p>NASA FIRMS thermal anomalies plus bounded nearby weather context, with source citations,
          stated limitations and a receipt for what was returned.</p>
        <div class="card-links"><a href="https://use.modelmarket.dev/ideas.html?id=fire-hotspot" target="_blank" rel="noopener">Walk the path</a></div>
      </div>

      <div class="card">
        <span class="pill live">callable SKU</span>
        <h3>ATLAS verified watchbox</h3>
        <p>One bounding box and a layer set returns current matches with explicit LIVE/SIM flags,
          coverage boundaries and a content receipt — agent-ready, no page to scrape.</p>
        <div class="card-links"><a href="https://use.modelmarket.dev/ideas.html?id=verified-watchbox" target="_blank" rel="noopener">Inspect the SKU</a>
          <a href="https://atlas.modelmarket.dev/" target="_blank" rel="noopener">Open ATLAS</a></div>
      </div>

      <div class="card">
        <span class="pill ready">build-ready</span>
        <h3>Flood hydrology evidence</h3>
        <p>US NWS flood alerts paired with river gauges inside a bbox, with citations and a receipt.
          Deliberately not a flood model and not a parametric quote.</p>
        <div class="card-links"><a href="https://use.modelmarket.dev/ideas.html?id=flood-hydrology" target="_blank" rel="noopener">Walk the path</a></div>
      </div>

      <div class="card">
        <span class="pill live">live</span>
        <h3>Learn it in clips</h3>
        <p>Short lessons on the agent economy — discovery, receipts, payment channels — for when
          you would rather watch the loop once before wiring it.</p>
        <div class="card-links"><a href="https://edu.modelmarket.dev/" target="_blank" rel="noopener">AIMarket School</a></div>
      </div>

      <div class="card">
        <span class="pill">pick a lane</span>
        <h3>See · Buy · Publish · Build · Invest</h3>
        <p>Five onboarding paths with the evidence behind each one, plus the idea boards for
          products the rails already support but nobody has built yet.</p>
        <div class="card-links"><a href="https://use.modelmarket.dev/#onboard" target="_blank" rel="noopener">Use-cases portal</a>
          <a href="https://use.modelmarket.dev/#boards" target="_blank" rel="noopener">Idea boards</a></div>
      </div>

      <div class="card">
        <span class="pill live">live</span>
        <h3>Run the hub yourself</h3>
        <p>One container, seeded from this hub's manifest. It federates on startup, so your
          capabilities are discoverable from here and vice versa. One docker run, one seed list.</p>
        <div class="card-links"><a href="/examples">All six integration methods</a></div>
      </div>

    </div>
  </section>

  <section class="section" id="protocol">
    <div class="section-head">
      <div class="section-title">What the protocol gives you</div>
    </div>
    <div class="grid">
      <div class="card"><h3>Discovery</h3><p>Any AI agent starts at <code>/.well-known/ai-market.json</code>
        and walks the federation from there.</p>
        <div class="card-links"><a href="/.well-known/ai-market.json">Try it</a></div></div>
      <div class="card"><h3>HTTP 402 payments</h3><p>Pay-per-call in on-chain USDC on Base, with
        pre-funded escrow channels for multi-step workflows.</p>
        <div class="card-links"><a href="/ai-market/v2/manifest">Manifest</a>
          <a href="https://basescan.org/address/__AIMARKET_ESCROW_ADDR__" target="_blank" rel="noopener">Escrow contract</a></div></div>
      <div class="card"><h3>Safety gate</h3><p>Every request passes safety classifiers. Injection,
        PII, medical — atomic abort, refund, and a signed rejection receipt.</p></div>
      <div class="card"><h3>Federation</h3><p>Crawl other hubs via <code>.well-known</code>, index
        their capabilities, route invocations. Search for AI marketplaces.</p></div>
      <div class="card"><h3>15 plugins</h3><p>Provenance receipts, reputation, TEE attestation,
        auctions, streaming, ZK proofs, NFT credits, personas, and more.</p>
        <div class="card-links"><a href="/plugins/demo">Live demo</a>
          <a href="/ai-market/v2/plugins">Catalog (JSON)</a></div></div>
      <div class="card"><h3>Live economy</h3><p>Real-time invocation feed, $/hour ticker,
        leaderboards — the terminal view of the whole federation.</p>
        <div class="card-links"><a href="/">Launch terminal</a></div></div>
    </div>
  </section>

  <section class="section" id="api">
    <div class="section-head"><div class="section-title">API reference</div></div>
    <div class="card" style="padding:6px 0 0;">
    <div class="table-wrap">
    <table>
      <thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>
      <tbody>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/.well-known/ai-market.json</code></td><td>Root discovery manifest</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/ai-market/v2/manifest</code></td><td>Federated capability catalog (signed)</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/ai-market/v2/search</code></td><td>NL federated search</td></tr>
      <tr><td><span class="tag tag-post">POST</span></td><td><code>/ai-market/v2/invoke</code></td><td>Federated invoke (safety-gated)</td></tr>
      <tr><td><span class="tag tag-post">POST</span></td><td><code>/ai-market/v2/channel/open</code></td><td>Open payment channel</td></tr>
      <tr><td><span class="tag tag-post">POST</span></td><td><code>/ai-market/v2/channel/close</code></td><td>Close channel, settle</td></tr>
      <tr><td><span class="tag tag-post">POST</span></td><td><code>/ai-market/v2/federation/announce</code></td><td>Peer hub announcement</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/ai-market/v2/plugins</code></td><td>Loaded plugins catalog</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/ai-market/v2/reputation/{hub}</code></td><td>Trust score for a hub</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/ai-market/v2/stats/live</code></td><td>Real-time invocation feed</td></tr>
      <tr><td><span class="tag tag-get">GET</span></td><td><code>/mcp</code></td><td>Hosted MCP endpoint — status, tools, trial policy</td></tr>
      </tbody>
    </table>
    </div>
    </div>
  </section>
</div>
"""

_EXAMPLES_BODY = r"""
<div class="shell">
  <header class="hero">
    <a class="eyebrow" href="/developers">← Start here first</a>
    <h1><span class="grad">Integration</span> Examples</h1>
    <p class="tagline">Every way to connect to the AI Economy — 6 integration methods and 15 plugin
      examples. New here? The <a href="/developers#start">three-door onboarding</a> is the shorter
      way in; this page is the reference behind it.</p>
    <div class="btn-row" style="margin-top:24px;">
      <a class="btn" href="/plugins/demo">Interactive plugin demo</a>
      <a class="btn btn-ghost" href="/widget/demo">Widget gallery</a>
      <a class="btn btn-ghost" href="https://use.modelmarket.dev/#cases" target="_blank" rel="noopener">Use cases</a>
    </div>
  </header>

  <div class="tabs">
    <button type="button" class="tab active" data-tab="methods">6 Integration Methods</button>
    <button type="button" class="tab" data-tab="plugins">15 Plugin Examples</button>
  </div>

<div id="tab-methods">
<div class="section"><div class="section-head"><div class="section-title">1 · <b>cURL</b> — quick discovery</div>
  <span class="pill free">no key, no wallet</span></div>
<pre><span class="c"># Discover the hub</span>
curl {HUB}/.well-known/ai-market.json

<span class="c"># Search capabilities</span>
curl "{HUB}/ai-market/v2/search?intent=translate+to+5+languages&amp;budget=3.00"

<span class="c"># Open channel + invoke + close</span>
<span class="n">CH</span>=$(curl -s -X POST {HUB}/ai-market/v2/channel/open \
  -H "Content-Type: application/json" \
  -d '{"deposit_usd":3.00}' | jq -r '.channel.channel_id')

curl -X POST {HUB}/ai-market/v2/invoke \
  -H "Content-Type: application/json" -H "X-Payment-Channel: $CH" \
  -d '{"product_id":"prd","capability_id":"cap@v1","source_hub":"local","input":{"text":"hello"}}'

curl -X POST {HUB}/ai-market/v2/channel/close \
  -H "Content-Type: application/json" -d "{\"channel_id\":\"$CH\"}"</pre></div>

<div class="section"><div class="section-head"><div class="section-title">2 · <b>Python SDK</b> — pip install aimarket-agent</div></div>
<pre><span class="c"># pip install aimarket-agent</span>
<span class="k">from</span> aimarket_agent <span class="k">import</span> AIMarketAgent

agent = AIMarketAgent(base_url=<span class="s">"{HUB}"</span>, budget=3.00)
result = agent.run(<span class="s">"translate spec to 5 languages + legal review"</span>)
print(f"Spent: ${result['total_spent_usd']:.2f}")</pre></div>

<div class="section"><div class="section-head"><div class="section-title">3 · <b>Widget embed</b> — one script tag</div>
  <div class="section-note"><a href="/widget/demo">Theme gallery →</a></div></div>
<pre><span class="c">&lt;!-- Add to any HTML page. The embedding site earns a share of widget spend --&gt;</span>
&lt;script src=<span class="s">"{HUB}/widget/widget.js"</span>
        data-theme=<span class="s">"cyber"</span>
        data-intent=<span class="s">"summarize this article"</span>
        data-budget=<span class="s">"3.00"</span>
        data-hub-url=<span class="s">"{HUB}"</span>
        data-affiliate-id=<span class="s">"my_blog"</span>&gt;&lt;/script&gt;</pre></div>

<div class="section"><div class="section-head"><div class="section-title">4 · <b>MCP</b> — Claude Desktop, Cursor, any client</div>
  <span class="pill free">free tier</span></div>
<div class="section-note" style="margin-bottom:12px;">The fastest path is the hosted endpoint or the
  published client — packaging your own capability as an MCP server is the step after that.</div>
<pre><span class="c"># the client: a few invokes per install, no wallet</span>
pip install aimarket-mcp
aimarket-mcp

<span class="c"># or point any MCP client at the hosted endpoint (streamable-http)</span>
{HUB}/mcp

<span class="c"># package your own capability as an MCP server</span>
pip install aimarket-mcp-packager</pre></div>

<div class="section"><div class="section-head"><div class="section-title">5 · <b>Deploy your own hub</b></div></div>
<pre>git clone https://github.com/alexar76/aimarket-hub.git
cd aimarket-hub
docker build -f Dockerfile.standalone -t aimarket-hub:local .
docker run --rm -p 127.0.0.1:9083:9083 \
  -e AIMARKET_HUB_NAME=<span class="s">"My Hub"</span> \
  -e AIMARKET_HUB_URL=<span class="s">"http://localhost:9083"</span> \
  -v aimarket-hub-data:/app/data \
  -e AIMARKET_SEED_LIST=<span class="s">"{HUB}/.well-known/ai-market.json"</span> \
  aimarket-hub:local</pre>
<p>Local discovery first. This does not publish a public hub or configure payments.
For HTTPS, identity backups and explicit federation admission, follow the
<a href="https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md">operator guide</a>.</p></div>

<div class="section"><div class="section-head"><div class="section-title">6 · <b>Federation CLI</b></div></div>
<pre><span class="c"># pip install aimarket-hub</span>
aimarket peers --base-url {HUB}
aimarket search <span class="s">"legal document review"</span> --base-url {HUB}
aimarket crawl --base-url {HUB}</pre></div>
</div>

<div id="tab-plugins" style="display:none">
<div class="btn-row" style="margin-bottom:18px;">
  <a class="btn" href="/plugins/demo">→ Interactive plugin demo</a>
  <a class="btn btn-ghost" href="/ai-market/v2/plugins">Plugin catalog (JSON)</a>
</div>
<p class="section-note" style="margin-bottom:18px;">Each plugin auto-discovers and registers with the
  hub at startup. Every name on this page is published on PyPI by this project — do not
  <code>pip install</code> an <code>aimarket-*</code> name this page does not list. Try live routes
  on the <a href="/plugins/demo">plugin demo page</a>.</p>
<div class="grid">

<div class="card"><h3>aimarket-provenance</h3><div class="cat">compliance</div><p>Ed25519 W3C VC receipts on every invoke. Auto-attached provenance_receipt with public verify URL.</p><code>pip install aimarket-provenance</code></div>

<div class="card"><h3>aimarket-safety</h3><div class="cat">security</div><p>Pre/post-invoke safety classifier. Blocks injection, PII, medical, harassment. Issues signed rejection receipts with auto-refund.</p><code>pip install aimarket-safety</code></div>

<div class="card"><h3>aimarket-reputation</h3><div class="cat">reputation</div><p>Stake-bond + signed outcomes + dispute resolution. On-chain reputation aggregation with bond slashing.</p><code>pip install aimarket-reputation</code></div>

<div class="card"><h3>aimarket-tee</h3><div class="cat">security</div><p>TEE-attested execution (AWS Nitro Enclaves / Intel TDX). Attestation reports + enclave-signed receipts. Enterprise compliance ready.</p><code>pip install aimarket-tee</code></div>

<div class="card"><h3>aimarket-auction</h3><div class="cat">monetization</div><p>Spot bidding market. Post tasks, providers bid in real-time, consumer picks winner. Uber-vibes for AI tasks.</p><code>pip install aimarket-auction</code></div>

<div class="card"><h3>aimarket-personas</h3><div class="cat">tooling</div><p>Auto-generated AI agent personas per product. Names (Lyra, Nova...), CVs, avatars, greetings. Chat-native discovery.</p><code>pip install aimarket-personas</code></div>

<div class="card"><h3>aimarket-data-cap</h3><div class="cat">monetization</div><p>Data-as-capability. Upload private corpus → becomes paid RAG-capability. 70% revenue to data owner.</p><code>pip install aimarket-data-cap</code></div>

<div class="card"><h3>aimarket-nft</h3><div class="cat">monetization</div><p>Tokenized pre-paid credits (ERC-721). Transfer, gift, sell on secondary market. Liquidity for unused calls.</p><code>pip install aimarket-nft</code></div>

<div class="card"><h3>aimarket-mcp-packager</h3><div class="cat">tooling</div><p>Package any capability as MCP server. Docker image + manifest + Claude Desktop config. One-click install.</p><code>pip install aimarket-mcp-packager</code></div>

<div class="card"><h3>aimarket-orchestrator</h3><div class="cat">monetization</div><p>Orchestrator as a capability. NL task → plan → execute chain → BOM. Sells the brain, not just muscles. 1% fee.</p><code>pip install aimarket-orchestrator</code></div>

<div class="card"><h3>aimarket-streaming</h3><div class="cat">monetization</div><p>SSE/WS streaming + per-chunk billing. Micro-receipts every N tokens. Cancel mid-stream, pay only for received.</p><code>pip install aimarket-streaming</code></div>

<div class="card"><h3>aimarket-promo</h3><div class="cat">monetization</div><p>Signed time-locked discount offers. Yield Management for AI. Providers pop demand when spare capacity.</p><code>pip install aimarket-promo</code></div>

<div class="card"><h3>aimarket-dataset</h3><div class="cat">tooling</div><p>Weekly anonymized invocation corpus (JSONL). CC-BY 4.0. Researchers cite, orchestrator trains on it.</p><code>pip install aimarket-dataset</code></div>

<div class="card"><h3>aimarket-zk</h3><div class="cat">security</div><p>ZK input/output proofs. Prove input matches schema without revealing it. Prove execution correctness without revealing trace.</p><code>pip install aimarket-zk</code></div>

<div class="card"><h3>aimarket-channels</h3><div class="cat">infrastructure</div><p>Pre-funded payment channels. Off-chain ledger, on-chain settlement. Debit/refund API. 24h auto-expiry.</p><code>pip install aimarket-channels</code></div>

</div>
</div>
</div>

<script>
document.querySelectorAll(".tab").forEach(function (tab) {
  tab.addEventListener("click", function () {
    var name = tab.getAttribute("data-tab");
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t === tab); });
    document.querySelectorAll('[id^="tab-"]').forEach(function (d) {
      d.style.display = d.id === "tab-" + name ? "block" : "none";
    });
  });
});
</script>
"""

_OFFSITE_HOSTS = ("use.modelmarket.dev", "atlas.modelmarket.dev", "edu.modelmarket.dev")

#: A whole `<div class="card">…</div>` block at the section's indentation.
_CARD_RE = re.compile(r"\n      <div class=\"card\">.*?\n      </div>\n", re.DOTALL)
#: An anchor to one of the reference ecosystem's other properties.
_OFFSITE_LINK_RE = re.compile(
    r"<a (?P<attrs>[^>]*href=\"https://(?:use|atlas|edu)\.modelmarket\.dev[^\"]*\"[^>]*)>"
    r"(?P<label>.*?)</a>",
    re.DOTALL,
)
#: A paragraph whose whole point is a link to a chain explorer.
_PROOF_P_RE = re.compile(r"\n *<p[^>]*>(?:(?!</p>).)*?basescan\.org.*?</p>", re.DOTALL)
#: Any remaining explorer anchor (an "Escrow contract" link in a card's link row).
_EXPLORER_LINK_RE = re.compile(
    r"\s*<a href=\"https://basescan\.org[^\"]*\"[^>]*>.*?</a>", re.DOTALL,
)


def _localise(body: str, hub_url: str, ecosystem_links: bool) -> str:
    """Make a page describe THIS hub.

    Three different problems shared one symptom — a stranger's page advertising
    modelmarket.dev — and they need different treatment:

    * **Wrong address.** Every copy-pasteable sample named another hub, so a reader who
      followed the documentation called somebody else's hub. That is `{HUB}`, and it is
      substituted always.
    * **Somebody else's satellites.** Cards and links pointing at the reference ecosystem's
      use-case portal, ATLAS and school. Correct on the reference deployment, advertising
      on anyone else's, and there is no local equivalent to redirect them to — so the cards
      go whole and prose links keep their words without the destination.
    * **Somebody else's evidence.** Three Basescan transactions and an escrow address,
      offered as this page's proof that settlement really happens. On another operator's
      hub that is a claim about work they did not do, which is worse than showing nothing.

    ``ecosystem_links`` is the single question behind the last two: is this deployment the
    reference one whose satellites and receipts these are?
    """
    out = body.replace("{HUB}", (hub_url or "").rstrip("/"))
    # The escrow address is a TOKEN in the page bodies, not a literal: these are plain
    # triple-quoted strings (a brace expression would render as visible text), and the
    # address moves on a redeploy. Substituted before the early return so the reference
    # deployment gets the live address; every other deployment has the whole link stripped
    # below anyway, because it is evidence of work that operator did not do.
    out = out.replace("__AIMARKET_ESCROW_ADDR__", _escrow_address())
    if ecosystem_links:
        return out
    out = _CARD_RE.sub(
        lambda m: "\n" if any(h in m.group(0) for h in _OFFSITE_HOSTS) else m.group(0), out,
    )
    # A button with nowhere to go is not a button; a sentence missing one link still reads.
    out = _OFFSITE_LINK_RE.sub(
        lambda m: "" if 'class="btn' in m.group("attrs") else m.group("label"), out,
    )
    out = _PROOF_P_RE.sub("", out)
    return _EXPLORER_LINK_RE.sub("", out)


def _page(body: str, title: str, description: str, active: str,
          hub_url: str, ecosystem_links: bool, lang: str = "en") -> str:
    lang = lang if lang in COPY else "en"
    copy = COPY[lang]
    path = "/examples" if active == "examples" else "/developers"
    switcher = '<nav class="btn-row" aria-label="Language">' + ''.join(
        f'<a class="btn btn-ghost" href="{path}?lang={code}" lang="{code}"'
        + (' aria-current="page"' if code == lang else '') + f'>{label}</a>'
        for code, label in (("en", "EN"), ("ru", "RU"), ("es", "ES"), ("fr", "FR"), ("zh", "中文"))
    ) + '</nav>'
    routes = [(f'/start?lang={lang}', copy[7])]
    if ecosystem_links:
        routes = [
            (f'https://play.modelmarket.dev/start?role=provider&amp;lang={lang}', copy[4]),
            (f'https://play.modelmarket.dev/start?role=consumer&amp;lang={lang}', copy[5]),
            (f'https://play.modelmarket.dev/publish?lang={lang}', copy[6]),
        ] + routes
    entry = '<section class="shell section">' + switcher + f'<h1>{escape(copy[2])}</h1><p>{escape(copy[3])}</p><div class="btn-row">'
    entry += ''.join(f'<a class="btn btn-ghost" href="{url}">{escape(label)}</a>' for url, label in routes)
    entry += f'</div><p><a href="/developers?lang={lang}">{escape(copy[0])}</a> · <a href="/examples?lang={lang}">{escape(copy[1])}</a></p></section>'
    reference = _localise(body, hub_url, ecosystem_links)
    if lang != "en":
        reference = f'<details class="shell"><summary>{escape(copy[8])}</summary><div lang="en">{reference}</div></details>'
    return theme.drop_missing_links(
        f'<!DOCTYPE html><html lang="{lang}"><head>'
        + theme.head_html(title, description)
        + "</head><body>"
        + theme.backdrop_html()
        + theme.nav_html(active)
        + entry + reference
        + theme.footer_html()
        + "<script>"
        + theme.COPY_JS
        + "</script></body></html>"
    )


def docs_html(hub_url: str = "", ecosystem_links: bool | None = None, lang: str = "en") -> str:
    """The /developers page, rendered for whoever is actually serving it."""
    return _page(
        _DOCS_BODY,
        f"{theme.BRAND['name']} — AI Economy Protocol",
        "Open protocol for AI-to-AI commerce: discovery, HTTP 402 payments, safety-gated invoke. "
        "Start with curl, then MCP without a wallet, then paid escrow channels.",
        "developers",
        hub_url or str(theme.BRAND.get("hub_url") or ""),
        bool(theme.BRAND.get("ecosystem_links")) if ecosystem_links is None else ecosystem_links,
        lang,
    )


def integration_examples_html(hub_url: str = "", ecosystem_links: bool | None = None, lang: str = "en") -> str:
    """The /examples page, rendered for whoever is actually serving it."""
    return _page(
        _EXAMPLES_BODY,
        f"Integration Examples — {theme.BRAND['name']}",
        "Six ways to connect to the AI Economy — cURL, Python SDK, widget embed, MCP, your own hub, "
        "federation CLI — plus 15 hub plugins.",
        "examples",
        hub_url or str(theme.BRAND.get("hub_url") or ""),
        bool(theme.BRAND.get("ecosystem_links")) if ecosystem_links is None else ecosystem_links,
        lang,
    )


def __getattr__(name: str) -> str:
    """`DOCS_HTML` / `INTEGRATION_EXAMPLES_HTML` as module attributes.

    They were module constants built at import, which froze one hub's address into the page
    before any configuration had been read. Resolving them on access means the same names
    keep working and now render for the hub that is actually serving.
    """
    if name == "DOCS_HTML":
        return docs_html()
    if name == "INTEGRATION_EXAMPLES_HTML":
        return integration_examples_html()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
