export type BlogBodyBlock =
  | { type: 'p'; text: string }
  | { type: 'h2'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'ul'; items: string[] }
  /** Product launch posts: place PNG/WebP/SVG under `web/frontend/public/blog/`. */
  | { type: 'img'; src: string; alt: string; caption?: string }
  /** Inline link to `/product/{productId}` (use real `prod-*` id when publishing). */
  | { type: 'product_link'; productId: string; label?: string };

export type BlogRelatedProduct = {
  productId: string;
  /** Defaults to “Product page”. */
  label?: string;
};

export type BlogPost = {
  slug: string;
  title: string;
  excerpt: string;
  publishedAt: string;
  readTime: string;
  tags: string[];
  author?: string;
  /** Shown under the excerpt — storefront URLs `/product/{productId}`. */
  relatedProducts?: BlogRelatedProduct[];
  body: BlogBodyBlock[];
};

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: 'how-to-generate-10-landing-pages-fast',
    title: 'How We Actually Ship Ten Landing Pages Without Turning Them Into Thin Spam',
    excerpt:
      'Batch generation sounds magical until you end up with ten variants that all say the same thing in slightly different fonts. Here is the messy middle ground that still ships fast.',
    publishedAt: '2026-05-07',
    readTime: '12 min',
    tags: ['growth', 'batch pipeline', 'landing pages'],
    author: 'Morgan Reeves',
    body: [
      {
        type: 'p',
        text:
          'I used to treat “generate ten landing pages” like ordering appetizers at a busy restaurant: shout the SKUs and hope something edible arrives. The pipeline cheerfully complied—every page had a hero, three bullets, and a primary button—but nobody believed them. Traffic bounced because each variant smelled algorithmically plausible rather than personally convincing.',
      },
      {
        type: 'p',
        text:
          'The breakthrough wasn’t model prompts alone; it was framing landings like paired comparisons instead of lottery tickets. Every candidate idea became “who hurts”, “what they fear admitting”, “what feels credible tomorrow”, and one ruthless constraint that differs across variants.',
      },
      {
        type: 'h2',
        text: 'Start narrow enough that humans could argue about specifics',
      },
      {
        type: 'p',
        text:
          'Spreadsheet paralysis sneaks in when prompts drift toward vibes (“better onboarding”). Rewrite prompts until your teammate argues whether messaging skews toward CTO guilt versus founding-team burnout—that specificity survives templating.',
      },
      {
        type: 'ul',
        items: [
          'One job-to-be-done per page (avoid stacking personas unless your segmentation pipeline proves lift)',
          'A headline lane measured against embarrassment (“would someone screenshot this?”) rather than cleverness',
          'Evidence placeholders baked early—quotes, metrics, logos—even if half ship as validated externally pending',
          'Single measurable outcome above the fold: signup, waitlist, or guided demo—never three competing CTAs',
        ],
      },
      {
        type: 'quote',
        text:
          'AI drafts behave better when they imitate ruthless critique circles rather than polite brainstorming circles.',
      },
      {
        type: 'h2',
        text: 'Batch mode beats heroic prompting because friction hides in naming',
      },
      {
        type: 'p',
        text:
          'Generate filenames that survive Slack archaeology (`pain-paywall-vs-pay-later-founders.md`), slug lineage mirrors experimentation hypotheses (`pricing-confidence-vs-security-paranoia`). Retrieval bots—and sleepy teammates scanning dashboards—thank you weeks later.',
      },
      {
        type: 'p',
        text:
          'QA gates earn skeptic eyeballs rather than checkbox vibes if benchmarks articulate rejection verbs (“reject vagueness”, “reject symmetrical clichés”). Automated tooling shines brightest routing mediocre-but-readable drafts back into iteration buckets instead of silently merging bad variants.',
      },
      {
        type: 'h2',
        text: 'Publish fewer pages publicly and obsess over comparison loops',
      },
      {
        type: 'p',
        text:
          'Ship three genuinely differentiated pages plus placeholder shells for internal debates before blasting DNS everywhere. Track engagement deltas qualitatively—people forwarding screenshots beats vanity CTR spikes.',
      },
      {
        type: 'p',
        text:
          'After launch, resist rewriting winners wholesale; mutate headlines while preserving narrative spine so attribution chatter stays intelligible during retro pizza debates.',
      },
    ],
  },
  {
    slug: 'discovery-phase-for-serious-products',
    title: 'Discovery Isn’t a Workshop Deck—It’s Defense Against Self-Lying Founders',
    excerpt:
      'Continuous discovery protects builders from seductive ideas backed only by caffeine and optimism. Here’s how signal hygiene beats brainstorming theater.',
    publishedAt: '2026-05-06',
    readTime: '13 min',
    tags: ['discovery', 'strategy', 'product'],
    author: 'Casey Alvarez',
    body: [
      {
        type: 'p',
        text:
          'Three summers ago I incubated an AI workflow assuming procurement managers secretly hated spreadsheets more than they hated procurement theater. The hypothesis sounded cinematic until interviews politely surfaced reality: nobody loses sleep over CSV merges—they lose sleep about audits.',
      },
      {
        type: 'p',
        text:
          'Automating discovery doesn’t replace instinct; it stops founders from narrativizing cherry-picked anecdotes into destiny arcs.',
      },
      {
        type: 'h2',
        text: 'Treat signals like instrumentation with uptime graphs',
      },
      {
        type: 'p',
        text:
          'Noise spikes whenever novelty floods timelines—GitHub trending repos, AI newsletters breathlessly claiming paradigm shifts. Separate novelty spikes from sustained irritation loops bubbling inside niche forums where practitioners swear casually.',
      },
      {
        type: 'ul',
        items: [
          'Blend qualitative shards (verbatim frustrations) with quantitative breadcrumbs (GitHub issue velocity, repeated Reddit threads)',
          'Document counter-evidence mercilessly—the memo defending why NOT to build matters more than cheerleader Slack screenshots',
          'Rotate sources deliberately so algorithmic drift doesn’t trap you inside identical bubble chambers weekly',
        ],
      },
      {
        type: 'quote',
        text:
          "Ranking isn't cruelty—it's compassion toward engineers whose calendars deserve protecting.",
      },
      {
        type: 'h2',
        text: 'Scorecards translate vibes into debate-able bets',
      },
      {
        type: 'p',
        text:
          'Evidence density beats vibes-only prioritization. Differentiation cannot merely sound poetic—it needs comparative anchors (“why won’t incumbent X ship this quarter?”). Feasibility weighs skeleton-team realities versus fantasy infinite-contractor timelines.',
      },
      {
        type: 'p',
        text:
          'Auto-enqueue top-ranked candidates only after humans sanity-check scoring skew—otherwise automation confidently executes brilliantly optimized nonsense.',
      },
      {
        type: 'h2',
        text: 'Discovery ceremonies decay unless rituals repeat boringly',
      },
      {
        type: 'p',
        text:
          'Weekly reruns beat quarterly ceremonies because markets mutate faster than quarterly OKR grids refresh. Treat stale rankings like flaky CI—surface amber warnings instead of silently pretending priorities froze correctly.',
      },
      {
        type: 'p',
        text:
          'Serious teams ritualize retiring hypotheses loudly—celebrate killing ideas compassionately so teammates pitch sharper replacements without fearing reputational tombstones.',
      },
    ],
  },
  {
    slug: 'from-free-tier-to-maker-with-stripe',
    title: 'Monetizing Without Feeling Like You’re Nickel-and-Diming Friends',
    excerpt:
      'Free tiers build empathy debts unless limits communicate fairness. Stripe wiring matters tactically; psychology gates conversions sustainably.',
    publishedAt: '2026-05-05',
    readTime: '11 min',
    tags: ['monetization', 'stripe', 'saas'],
    author: 'Dana Frost',
    body: [
      {
        type: 'p',
        text:
          'Early adopters sometimes behave like houseguests rinsing dishes—you adore them, yet secretly resent unclear checkout etiquette if generosity silently bankrupts compute budgets. Monetization conversations panic founders because pricing triggers shame reflexes inherited from awkward lemonade stands.',
      },
      {
        type: 'p',
        text:
          'Healthy conversions emerge when limits narrate mutual sustainability rather than punishment arcs.',
      },
      {
        type: 'h2',
        text: 'Transparent caps outperform mystery throttling',
      },
      {
        type: 'p',
        text:
          'Spell ceilings plainly (“500 guided generations monthly”) before frustration spikes—surprise walls trigger rage tweets faster than calm explanations inviting upgrades.',
      },
      {
        type: 'ul',
        items: [
          'Surface consumption dashboards embedded inside workflows so guilt converts into constructive pacing instead of stealth resentment',
          'Pair limits with tangible unlock stories (“priority sandbox teardowns”, “SOC-style audit trails”) instead of abstract “Pro badge” fluff',
          'Send pre-limit emails leaning cooperative (“you’re almost maxed—we’ll pause politely”) versus melodramatic cliffhangers',
        ],
      },
      {
        type: 'quote',
        text:
          'Upgrade prompts succeed when they resemble courteous bartenders offering another drink—not repo tow trucks threatening repos.',
      },
      {
        type: 'h2',
        text: 'Checkout friction audits deserve obsessive pessimism',
      },
      {
        type: 'p',
        text:
          'Stripe webhook elegance separates serene sleeps from “why didn’t entitlements flip?” incident retrospectives. Automate subscription mirrors testing unhappy paths—partial refunds, card declines mid-batch jobs, timezone renewal quirks.',
      },
      {
        type: 'p',
        text:
          'Human reassurance loops complement receipts—short confirmation copy acknowledging nervous CFO instincts converts skeptical champions internally.',
      },
      {
        type: 'h2',
        text: 'Benchmark transparency earns wallet taps before invoices arrive',
      },
      {
        type: 'p',
        text:
          'Publishing reproducible performance narratives—even imperfect snapshots—signals adulthood versus vapor vibes. Prospects mentally amortize price tags against confidence accrued quietly.',
      },
      {
        type: 'p',
        text:
          'Iterate ladders aggressively during seasons shifting buyer personas—students crave lifetime sparks while agency operators crave predictable seats.',
      },
    ],
  },
  {
    slug: 'launch-fleetpulse-iot-live-device-grid',
    title: 'Launch: FleetPulse IoT — live device grid, filters, and telemetry drill-down',
    excerpt:
      'What shipped in the sandbox, how facility managers navigate sites and buildings, and how we validated MQTT-backed freshness without turning the UI into a wall of JSON.',
    publishedAt: '2026-05-10',
    readTime: '8 min',
    tags: ['product launch', 'iot', 'sandbox'],
    author: 'AI-Factory Launch Notes',
    relatedProducts: [
      {
        productId: 'prod-demo-market-01',
        label: 'Example product page (replace with this release’s prod id)',
      },
    ],
    body: [
      {
        type: 'p',
        text:
          'FleetPulse targets operators who already run CMMS spreadsheets but still ping battery thresholds in Slack. This release is not “another dashboard”—it is a tight loop between device truth, last-seen confidence, and an alert timeline that respects on-call dignity.',
      },
      {
        type: 'h2',
        text: 'What you get in the first session',
      },
      {
        type: 'p',
        text:
          'The landing story stays modest: pick a site, scan the grid, open one device, read signal quality and raw telemetry without losing context. Filters stick while you move between buildings so you are not re-clicking the same chips after every navigation.',
      },
      {
        type: 'ul',
        items: [
          'Grid columns: device id, battery %, last MQTT ping, RSSI where the gateway exposes it',
          'Site / building filters with counts so empty states explain themselves',
          'Drill-down: raw telemetry JSON plus a compact alert timeline for that device',
        ],
      },
      {
        type: 'img',
        src: '/blog/launch-sandbox-preview.svg',
        alt: 'FleetPulse sandbox UI preview',
        caption: 'Sandbox preview — swap file for your captured PNG when you publish.',
      },
      {
        type: 'h2',
        text: 'Why MQTT freshness matters more than chart glitter',
      },
      {
        type: 'p',
        text:
          'Operators forgive ugly charts; they do not forgive silent devices. The UI foregrounds last ping age and degrades gracefully when a gateway drops—no fake smooth curves stitched across outages.',
      },
      {
        type: 'quote',
        text:
          'If the grid cannot answer “is this device lying to me?” in two seconds, it is enterprise theater.',
      },
      {
        type: 'h2',
        text: 'Operator checklist we used before calling this “launched”',
      },
      {
        type: 'ul',
        items: [
          'Cold load under throttled network still renders grid skeleton + stale badges correctly',
          'Deep-linkable device panel for screenshots in incident threads',
          'REST surfaces for devices and sites documented beside the demo so API curious buyers are not blocked',
        ],
      },
      {
        type: 'img',
        src: '/blog/launch-pipeline-admin.svg',
        alt: 'Pipeline admin view during FleetPulse rollout',
        caption: 'Pipeline state while the build finishes — pair product screenshots with ops context.',
      },
      {
        type: 'p',
        text:
          'Next iterations will tighten websocket back-pressure under burst telemetry and add export hooks for CMMS tickets. For now: honest latency indicators beat speculative animations.',
      },
    ],
  },
  {
    slug: 'launch-tracerelay-webhook-inbox-replay',
    title: 'Launch: TraceRelay DevTools — webhook inbox, search, and replay safety rails',
    excerpt:
      'Shipping a developer-facing inbox means searchable captures, respectful retention defaults, and replay flows that do not become accidental forward spam.',
    publishedAt: '2026-05-09',
    readTime: '7 min',
    tags: ['product launch', 'devtools', 'webhooks'],
    author: 'AI-Factory Launch Notes',
    relatedProducts: [
      {
        productId: 'prod-demo-market-01',
        label: 'Example product page (replace with this release’s prod id)',
      },
    ],
    body: [
      {
        type: 'p',
        text:
          'TraceRelay sits where curl logs die: inbound HTTP becomes structured rows with headers, bodies, and replay targets. The launch focuses on discoverability—developers should recognize payload shapes faster than they grok jq one-liners.',
      },
      {
        type: 'h2',
        text: 'UX bets in this cut',
      },
      {
        type: 'ul',
        items: [
          'Register endpoints with obvious inbox URLs so README snippets stay copy-paste short',
          'Search across bodies and metadata without turning the table into a regex puzzle',
          'Replay stub that targets secondary URLs with explicit confirmation so devs do not weaponize mis-clicks',
        ],
      },
      {
        type: 'img',
        src: '/blog/launch-sandbox-preview.svg',
        alt: 'TraceRelay inbox table and capture detail',
        caption: 'Inbox + detail — replace with your PNG from the browser demo.',
      },
      {
        type: 'h2',
        text: 'Safety defaults over demo fireworks',
      },
      {
        type: 'p',
        text:
          'Replay is powerful and boring on purpose: confirm destination host, show payload size, block surprise external schemes unless explicitly enabled. The UI should feel like a cautious colleague forwarding email, not a shout into prod.',
      },
      {
        type: 'quote',
        text:
          'If replay feels frictionless, someone will replay into the wrong URL at 2am with conviction.',
      },
      {
        type: 'h2',
        text: 'What we validated before publishing the launch post',
      },
      {
        type: 'p',
        text:
          'Large payload paths (within demo limits) still render scrollable viewers; binary-ish bodies degrade to hex preview instead of freezing the tab. OpenAPI stays enabled so integrators can diff behavior against their own stubs.',
      },
      {
        type: 'img',
        src: '/blog/launch-pipeline-admin.svg',
        alt: 'Admin pipeline trace for TraceRelay build',
        caption: 'Optional second shot: pipeline or security report — tells a fuller ship story.',
      },
      {
        type: 'p',
        text:
          'Follow-up work targets signature verification helpers and team-scoped inboxes. Until then: capture fidelity and replay clarity remain the headline.',
      },
    ],
  },
];

export function getPostBySlug(slug: string): BlogPost | undefined {
  return BLOG_POSTS.find((post) => post.slug === slug);
}
