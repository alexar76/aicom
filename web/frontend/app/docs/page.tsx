'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Cpu,
  BookOpen,
  ChevronRight,
  Menu,
  X,
  Home,
  Settings,
  Zap,
  Shield,
  Bot,
  Coins,
  BarChart3,
  Rocket,
  FileText,
  ExternalLink,
  Search,
  ArrowLeft,
  Copy,
  Check,
  Terminal,
  Server,
  Globe,
  Lock,
  Users,
  DollarSign,
  RefreshCw,
  Code2,
  Palette,
  Crown,
  Workflow,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';

// ── Types ─────────────────────────────────────────────────────────────────

interface DocSection {
  id: string;
  title: string;
  icon: React.ElementType;
  content: React.ReactNode;
}

// ── Navigation Bar ────────────────────────────────────────────────────────

function DocNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2 group">
          <Cpu className="w-6 h-6 text-indigo-400 group-hover:text-indigo-300 transition-colors" />
          <span className="text-lg font-bold text-white">AI-Factory</span>
        </a>
        <div className="hidden md:flex items-center gap-6">
          <a href="/" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
            <Home className="w-4 h-4" />
            Home
          </a>
          <a href="/docs" className="flex items-center gap-1.5 text-sm text-white transition-colors">
            <BookOpen className="w-4 h-4" />
            Docs
          </a>
          <a href="/admin" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
            <Settings className="w-4 h-4" />
            Admin
          </a>
        </div>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden text-gray-400 hover:text-white transition-colors"
          aria-label="Toggle menu"
        >
          {menuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>
      {menuOpen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:hidden border-t border-white/5 bg-black/90 backdrop-blur-xl"
        >
          <div className="px-4 py-3 space-y-2">
            <a href="/" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 text-sm text-gray-400 hover:text-white py-2 transition-colors">
              <Home className="w-4 h-4" /> Home
            </a>
            <a href="/docs" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 text-sm text-white py-2 transition-colors">
              <BookOpen className="w-4 h-4" /> Docs
            </a>
            <a href="/admin" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 text-sm text-gray-400 hover:text-white py-2 transition-colors">
              <Settings className="w-4 h-4" /> Admin
            </a>
          </div>
        </motion.div>
      )}
    </nav>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────

function DocSidebar({
  sections,
  activeSection,
  onSectionChange,
}: {
  sections: DocSection[];
  activeSection: string;
  onSectionChange: (id: string) => void;
}) {
  return (
    <aside className="w-64 flex-shrink-0 hidden lg:block">
      <nav className="sticky top-20 space-y-1">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <button
              key={section.id}
              onClick={() => onSectionChange(section.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                activeSection === section.id
                  ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{section.title}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

// ── Section Components ────────────────────────────────────────────────────

function CodeBlock({ code, language = 'bash' }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-4">
      <div className="absolute top-3 right-3 z-10">
        <button
          onClick={handleCopy}
          className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
          aria-label="Copy code"
        >
          {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <div className="text-xs text-gray-500 px-4 pt-2 pb-1">{language}</div>
      <pre className="bg-black/40 border border-white/5 rounded-xl p-4 overflow-x-auto text-sm text-gray-300 font-mono leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function InfoBox({ title, children, variant = 'info' }: { title: string; children: React.ReactNode; variant?: 'info' | 'warning' | 'success' }) {
  const colors = {
    info: 'border-indigo-500/30 bg-indigo-500/5',
    warning: 'border-amber-500/30 bg-amber-500/5',
    success: 'border-emerald-500/30 bg-emerald-500/5',
  };
  const icons = {
    info: FileText,
    warning: Shield,
    success: Check,
  };
  const Icon = icons[variant];

  return (
    <div className={`flex gap-3 p-4 rounded-xl border ${colors[variant]} my-4`}>
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5 text-indigo-400" />
      <div>
        <p className="text-sm font-medium text-white mb-1">{title}</p>
        <div className="text-sm text-gray-400">{children}</div>
      </div>
    </div>
  );
}

function DocScreenshot({ src, caption }: { src: string; caption: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="my-6">
      <div className="rounded-xl border border-white/10 overflow-hidden bg-gradient-to-br from-slate-900/90 to-indigo-950/50 shadow-lg shadow-indigo-500/5">
        {!failed ? (
          // eslint-disable-next-line @next/next/no-img-element -- static docs assets in /public/docs-screenshots
          <img src={src} alt="" className="w-full block" onError={() => setFailed(true)} />
        ) : (
          <div className="p-10 text-center text-sm text-gray-400 space-y-2">
            <p className="text-gray-300 font-medium">Screenshot not bundled</p>
            <p>
              From <code className="text-cyan-400/90">web/frontend</code> run{' '}
              <code className="text-cyan-400/90">npm run capture-docs-screenshots</code> with the app reachable (
              <code className="text-cyan-400/90">DOCS_SCREENSHOT_BASE_URL</code>,{' '}
              <code className="text-cyan-400/90">ADMIN_PASSWORD</code>).
            </p>
          </div>
        )}
      </div>
      <figcaption className="text-xs text-gray-500 mt-2 tracking-wide">{caption}</figcaption>
    </figure>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xl font-semibold text-white mt-8 mb-3">{children}</h3>;
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return <p className="text-gray-400 leading-relaxed mb-3">{children}</p>;
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2 my-3">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-gray-400">
          <ChevronRight className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

// ── Documentation Sections ────────────────────────────────────────────────

const docSections: DocSection[] = [
  {
    id: 'overview',
    title: 'Overview',
    icon: BookOpen,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          <span className="text-gradient">AI-Factory v2.1</span>
        </h2>
        <Badge variant="info" className="mb-6">AI Company Platform · Single Docker Stack</Badge>

        <Paragraph>
          Production-grade stack in one container (FastAPI + Next.js).{' '}
          <strong className="text-gray-200">One multi-agent pipeline</strong> for everything:{' '}
          <strong className="text-gray-200">autonomous</strong> mode feeds market research and generated ideas;{' '}
          <strong className="text-gray-200">on-demand</strong> mode starts from the customer&apos;s phrase — same stages,
          same QA gates. Typical deliverables are share-ready landings; crypto checkout and sandbox preview ship with the bundle.
        </Paragraph>

        <SubHeading>Core Capabilities</SubHeading>
        <List items={[
          'Twelve specialized pipeline roles in the admin roster: Analyst, PM, Methodologist, Architect, Designer (UX), Developer, QA, Security, DevOps, Marketing, Sales, and Evolution Analyst — plus Director as a meta-agent; `ui_experience` in architecture is the binding UX brief for the Developer',
          'Multi-LLM routing with failover — local Ollama, DeepSeek, Together, Groq',
          'Director AI — scheduled analysis, decisions queue, reports',
          'Crypto storefront — USDT/USDC (Base, Arbitrum, Ethereum, Solana); default list ~$4.99 USDT when sales artifacts omit price',
          'Glass storefront & admin — animations, responsive layout',
          'Enterprise-minded ops — secrets paths, audit hooks, sandbox isolation',
          'CLI companion for operators (`ai-company` where installed)',
          'Evolution loop — telemetry-driven improvements',
        ]} />

        <SubHeading>At a glance</SubHeading>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 my-4">
          {[
            { label: 'Deploy model', value: 'Compose' },
            { label: 'Quality gates', value: 'Demo + QA' },
            { label: 'Pricing default', value: '~$5' },
            { label: 'Stack depth', value: 'Full' },
          ].map((stat) => (
            <div key={stat.label} className="glass-card p-4 text-center">
              <div className="text-2xl font-bold text-white" dangerouslySetInnerHTML={{ __html: stat.value }} />
              <div className="text-xs text-gray-500 mt-1">{stat.label}</div>
            </div>
          ))}
        </div>

        <InfoBox title="Single Container" variant="info">
          Everything runs in one Docker container (Ubuntu 24.04, Python 3.12, Node.js 20). No external dependencies required.
        </InfoBox>

        <InfoBox title="Canonical handbook (Markdown)" variant="success">
          For printable diagrams (Mermaid), full scenario tables, and pitfalls see{' '}
          <code className="text-cyan-300">docs/owner-guide.md</code> in the repository — kept in sync with this tab.
        </InfoBox>
      </div>
    ),
  },
  {
    id: 'owner-guide',
    title: 'Owner playbook',
    icon: Crown,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4 flex items-center gap-3">
          <Crown className="w-9 h-9 text-amber-400" />
          <span>
            Platform <span className="text-gradient-primary">owner playbook</span>
          </span>
        </h2>
        <Badge variant="info" className="mb-6">
          Operator scenarios · Storefront policy · Support vs pipeline
        </Badge>

        <Paragraph>
          This section is for the person running a deployed instance: provisioning LLMs, watching the pipeline, curating the
          marketplace, and helping buyers. Deep tab reference lives in <code className="text-cyan-400">docs/admin-guide.md</code>
          ; REST patterns in <code className="text-cyan-400">docs/api-integration-guide.md</code>.
        </Paragraph>

        <SubHeading>Visual map</SubHeading>
        <GlassCard className="p-6 my-4 overflow-x-auto">
          <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm mb-4">
            <Workflow className="w-5 h-5" />
            Operator control plane
          </div>
          <div className="font-mono text-[13px] text-gray-300 leading-relaxed min-w-[42rem]">
            <div className="text-indigo-300 mb-1">┌──────────────┐     JWT cookie / Bearer</div>
            <div className="text-indigo-300 mb-1">│  Admin /admin│ ─────────────────────────► FastAPI /api/admin/*</div>
            <div className="text-indigo-300 mb-3">└──────────────┘                         │</div>
            <div className="text-emerald-300 mb-1">┌──────────────┐     public JSON          ▼</div>
            <div className="text-emerald-300 mb-1">│ Storefront / │ ───────────────────► /api/products · sandbox · support …</div>
            <div className="text-emerald-300 mb-3">└──────────────┘                         │</div>
            <div className="text-gray-500 mb-1 pl-16">pipeline worker ◄────► /app/data bind mount</div>
            <div className="text-gray-500 pl-16">Lumen (support) ────────► NOT a pipeline agent card</div>
          </div>
        </GlassCard>

        <SubHeading>Step-by-step — first day</SubHeading>
        <List items={[
          'Confirm a host bind mount for /app/data (see root README — avoid anonymous Docker volumes).',
          'Sign in at /admin/login and rotate the admin password; enable TOTP if desired.',
          'Open LLM Providers — wire at least one model backend and verify routing rules.',
          'Submit an idea from New Product or run CLI discover / create-idea inside the container.',
          'Watch Pipeline — expand a card, click stage tiles for task payloads and errors.',
          'Optional: run README full_pipeline_smoke.py against a completed product ID.',
        ]} />

        <SubHeading>Step-by-step — marketplace curation</SubHeading>
        <List items={[
          'Locate a COMPLETED row → Storefront panel.',
          'Edit Marketplace copy to tune card/detail text (persisted to marketing_content.json).',
          'If automatic quality gates block listing but you accept the risk: Force public storefront + justification.',
          'To pull a SKU offline: Not pursuing (with reason) or Hide from public storefront — shoppers lose listing + detail 404.',
          'Remember: Dashboard “Completed” counts lifecycle; storefront visibility adds code + quality + hide rules.',
        ]} />

        <SubHeading>Use-case snapshots</SubHeading>
        <div className="grid md:grid-cols-2 gap-4 my-4">
          {[
            {
              title: 'Burst intake',
              body: 'CLI create-ideas-batch or POST /api/admin/products/create-batch after validating LLM quota.',
            },
            {
              title: 'Stuck stage',
              body: 'Pipeline modal → inspect failing agent → LLM Logs + provider routing → optional human rework.',
            },
            {
              title: 'Buyer confusion',
              body: 'Lumen (/api/support) handles chat; tune RAG baseline markdown under backend services if branding changes.',
            },
            {
              title: 'Discovery backlog',
              body: 'Director discovery ranking → enqueue winners — documented in README + pipeline-operations.md.',
            },
          ].map((card) => (
            <GlassCard key={card.title} className="p-4 border border-white/10">
              <h4 className="text-white font-semibold mb-2">{card.title}</h4>
              <p className="text-sm text-gray-400 leading-relaxed">{card.body}</p>
            </GlassCard>
          ))}
        </div>

        <SubHeading>Listing decision flow</SubHeading>
        <GlassCard className="p-6 my-4 font-mono text-[13px] text-gray-300 leading-relaxed">
          <div className="text-cyan-400 mb-2">Shipped + code on disk?</div>
          <div className="pl-4 border-l border-white/10 mb-2">
            No → <span className="text-gray-500">never listed</span>
          </div>
          <div className="text-cyan-400 mb-2">Hidden / Not pursuing?</div>
          <div className="pl-4 border-l border-white/10 mb-2">
            Yes → <span className="text-rose-300">404 on public catalog + detail</span>
          </div>
          <div className="text-cyan-400 mb-2">Passes marketplace quality OR admin force-list?</div>
          <div className="pl-4 border-l border-white/10">
            Yes → <span className="text-emerald-300">visible on storefront</span>
          </div>
        </GlassCard>

        <SubHeading>Screenshots</SubHeading>
        <Paragraph>Captured into the repo and mirrored to <code className="text-cyan-400">/docs-screenshots/</code> for this page.</Paragraph>
        <DocScreenshot src="/docs-screenshots/admin-login.png" caption="Admin login — rotate credentials on day one." />
        <DocScreenshot src="/docs-screenshots/admin-dashboard.png" caption="Dashboard snapshot — differs from storefront-visible counts." />
        <DocScreenshot src="/docs-screenshots/admin-pipeline.png" caption="Pipeline monitor — storefront controls live inside expanded completed cards." />
        <DocScreenshot src="/docs-screenshots/admin-providers.png" caption="LLM Providers — keys, routing, health probes." />

        <InfoBox title="Mermaid diagrams & printable PDF" variant="info">
          GitHub renders the flowcharts in <code className="text-cyan-300">docs/owner-guide.md</code>. Copy that file into Notion,
          Confluence, or print-to-PDF for investor/operator packets.
        </InfoBox>
      </div>
    ),
  },
  {
    id: 'architecture',
    title: 'Architecture',
    icon: Server,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          System <span className="text-gradient-primary">Architecture</span>
        </h2>

        <Paragraph>
          AI-Factory follows a modular architecture with clear separation of concerns. All components run inside
          a single Docker container, communicating via internal HTTP and the filesystem.
        </Paragraph>

        <SubHeading>Component Diagram</SubHeading>
        <GlassCard className="p-6 my-4">
          <div className="font-mono text-sm text-gray-300 leading-relaxed">
            <div className="text-indigo-400 font-semibold mb-2">┌─────────────────────────────────────────┐</div>
            <div className="text-indigo-400 font-semibold">│         Docker Container (Ubuntu 24.04)         │</div>
            <div className="text-indigo-400 font-semibold mb-2">└─────────────────────────────────────────┘</div>
            <br />
            <div className="pl-4">
              <div className="text-cyan-400">├── AI Factory Core (Python)</div>
              <div className="pl-6 text-gray-500">│   ├── Orchestrator — LangGraph FSM</div>
              <div className="pl-6 text-gray-500">│   ├── 11 pipeline roles (incl. Designer/UX) + Director meta-agent</div>
              <div className="pl-6 text-gray-500">│   ├── Director AI — meta-agent scheduler</div>
              <div className="pl-6 text-gray-500">│   ├── LLM Router — provider abstraction</div>
              <div className="pl-6 text-gray-500">│   └── Security — firewall, secrets, audit</div>
              <br />
              <div className="text-green-400">├── Web Backend (FastAPI :8081)</div>
              <div className="pl-6 text-gray-500">│   ├── /api/products — storefront API</div>
              <div className="pl-6 text-gray-500">│   ├── /api/payment — crypto payments</div>
              <div className="pl-6 text-gray-500">│   ├── /api/sandbox — sandbox management</div>
              <div className="pl-6 text-gray-500">│   ├── /api/feedback — user feedback</div>
              <div className="pl-6 text-gray-500">│   ├── /api/support — Lumen (buyer support chat)</div>
              <div className="pl-6 text-gray-500">│   └── /api/admin — admin panel (JWT protected)</div>
              <br />
              <div className="text-amber-400">├── Web Frontend (Next.js :8080)</div>
              <div className="pl-6 text-gray-500">│   ├── / — Storefront main page</div>
              <div className="pl-6 text-gray-500">│   ├── /product/[id] — Product detail</div>
              <div className="pl-6 text-gray-500">│   ├── /checkout — Payment flow</div>
              <div className="pl-6 text-gray-500">│   └── /admin — Admin panel</div>
              <br />
              <div className="text-purple-400">├── Data Layer</div>
              <div className="pl-6 text-gray-500">│   ├── /data/config/ — YAML/JSON configs</div>
              <div className="pl-6 text-gray-500">│   ├── /data/state/ — Pipeline state</div>
              <div className="pl-6 text-gray-500">│   ├── /data/logs/ — Audit & app logs</div>
              <div className="pl-6 text-gray-500">│   ├── /data/reports/ — Director reports</div>
              <div className="pl-6 text-gray-500">│   └── /data/secrets/ — Encrypted secrets</div>
              <br />
              <div className="text-pink-400">└── CLI (ai-company command)</div>
              <div className="pl-6 text-gray-500">    └── Direct management via terminal</div>
            </div>
          </div>
        </GlassCard>

        <SubHeading>Request Flow</SubHeading>
        <Paragraph>
          User requests go to Next.js on port 8080. API calls to <code>/api/*</code> are proxied by Next.js rewrites
          to the FastAPI backend on port 8081. The admin panel is served by Next.js as well.
        </Paragraph>

        <CodeBlock code={`next.config.js:
// All /api/* requests are proxied to FastAPI backend
async rewrites() {
  return [
    { source: '/api/:path*', destination: 'http://localhost:8081/api/:path*' },
  ];
}`} language="javascript" />
      </div>
    ),
  },
  {
    id: 'quickstart',
    title: 'Quick Start',
    icon: Zap,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Quick <span className="text-gradient-primary">Start</span>
        </h2>

        <Paragraph>
          Deploy and run the AI-Factory platform with a single Docker command.
        </Paragraph>

        <SubHeading>1. Build the Image</SubHeading>
        <CodeBlock code={`docker build -t ai-factory .`} />

        <SubHeading>2. Run the Container</SubHeading>
        <CodeBlock code={`docker run -d \\
  --name ai-factory \\
  -v ./data:/app/data \\
  -p 8080:8080 \\
  ai-factory`} />

        <SubHeading>3. Access the Platform</SubHeading>
        <List items={[
          'Storefront: <a href="http://localhost:8080" class="text-indigo-400 hover:underline">http://localhost:8080</a>',
          'Admin Panel: <a href="http://localhost:8080/admin" class="text-indigo-400 hover:underline">http://localhost:8080/admin</a>',
          'API Docs: <a href="http://localhost:8080/api/docs" class="text-indigo-400 hover:underline">http://localhost:8080/api/docs</a> (FastAPI Swagger)',
        ]} />

        <SubHeading>4. Login to Admin</SubHeading>
        <Paragraph>
          Default credentials are generated on first startup and stored in <code>/app/data/config/admin.json</code>.
        </Paragraph>
        <List items={[
          'Username: <code>admin</code>',
          'Password: <code>admin123</code> (default, change immediately)',
          'Navigate to <code>/admin/login</code> and sign in',
        ]} />

        <SubHeading>5. Create Your First Product</SubHeading>
        <CodeBlock code={`# Via CLI
docker exec -it ai-factory python cli/ai_company_cli.py create-idea "Your product idea here"

# Or via Admin Panel
# Go to /admin → New Product tab → Submit idea`} />

        <InfoBox title="Docker-in-Docker" variant="info">
          The container includes Docker-in-Docker for sandbox isolation. If you need sandbox features,
          add <code>--privileged</code> or mount the Docker socket.
        </InfoBox>
      </div>
    ),
  },
  {
    id: 'admin-panel',
    title: 'Admin Panel',
    icon: Settings,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Admin <span className="text-gradient-primary">Panel</span>
        </h2>

        <Paragraph>
          The admin panel at <code>/admin</code> provides complete control over the AI-Factory platform.
          It is protected by JWT-based authentication with optional 2FA (TOTP).
        </Paragraph>

        <SubHeading>Authentication</SubHeading>
        <List items={[
          'JWT tokens with HTTP-only cookies',
          '30-minute inactivity auto-logout',
          'Brute-force protection: max 5 failed attempts per 15 minutes',
          'Optional 2FA via Google Authenticator (TOTP)',
        ]} />

        <SubHeading>Dashboard Tab</SubHeading>
        <Paragraph>
          Real-time metrics overview including:
        </Paragraph>
        <List items={[
          'Pipeline metrics — total/active/completed/failed products, pending/running/timed-out tasks',
          'Resource usage — CPU, memory, disk utilization',
          'Revenue — earnings over last 24h, 7d, 30d',
          'Security status — system health indicator, recent failed logins',
        ]} />

        <SubHeading>Model Providers Tab</SubHeading>
        <Paragraph>
          Configure and manage LLM providers:
        </Paragraph>
        <List items={[
          'View all configured providers with status (online/offline/degraded)',
          'Toggle providers enabled/disabled',
          'Monitor latency and model availability',
          'Configure routing rules per task type',
        ]} />

        <SubHeading>Agents Tab</SubHeading>
        <Paragraph>
          Monitor and configure AI agents:
        </Paragraph>
        <List items={[
          'View status of all 11 pipeline roles (including Designer)',
          'Configure timeouts, retry limits, and priorities',
          'View agent logs with filtering',
          'Restart individual agents if needed',
        ]} />

        <SubHeading>Security Tab</SubHeading>
        <Paragraph>
          Security monitoring and configuration:
        </Paragraph>
        <List items={[
          'View audit logs with date/action/user filters',
          'Export logs in JSON format',
          'Change admin password',
          'Configure 2FA',
        ]} />

        <SubHeading>Director Tab</SubHeading>
        <Paragraph>
          Director AI management:
        </Paragraph>
        <List items={[
          'View latest Director reports with metrics and recommendations',
          'Configure analysis frequency (1/2/4/12 hours)',
          'Toggle automatic actions on/off',
          'Trigger manual analysis for testing',
        ]} />

        <SubHeading>Settings Tab</SubHeading>
        <Paragraph>
          Storefront theme customization:
        </Paragraph>
        <List items={[
          'Choose from 5 themes: Cyberpunk, Minimal, Glass, Neon, Corporate',
          'Theme applies dynamically without page reload',
        ]} />
      </div>
    ),
  },
  {
    id: 'api-reference',
    title: 'API Reference',
    icon: Code2,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          API <span className="text-gradient-primary">Reference</span>
        </h2>

        <Paragraph>
          The FastAPI backend exposes a comprehensive REST API. All endpoints are accessible via
          <code>/api/*</code> through the Next.js proxy. Interactive documentation is available at
          <a href="/api/docs" className="text-indigo-400 hover:underline"> /api/docs</a> (Swagger UI). Raw schema:
          backend <code className="text-gray-300">/openapi.json</code>.
        </Paragraph>

        <InfoBox title="Integration handbook" variant="info">
          For authentication flows (cookie + Bearer), a grouped router map, curl snippets, and support-chat headers see{' '}
          <code className="text-cyan-300">docs/api-integration-guide.md</code>. Swagger stays authoritative after upgrades.
        </InfoBox>

        <SubHeading>Public Endpoints</SubHeading>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/health</code>
          </div>
          <p className="text-sm text-gray-400">System health check. Returns status, version, and service name.</p>
          <CodeBlock code={`Response:
{
  "status": "ok",
  "version": "2.1.0",
  "service": "ai-factory-backend"
}`} language="json" />
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/products</code>
          </div>
          <p className="text-sm text-gray-400">
            Storefront listing for shipped builds — filters incomplete sandboxes, marketplace quality, admin hide / not
            pursuing.
          </p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/products/{'{id}'}</code>
          </div>
          <p className="text-sm text-gray-400">
            Product detail for public storefront — hidden SKUs return <code className="text-gray-300">404</code>.
          </p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">MIXED</Badge>
            <code className="text-sm text-white">/api/support/*</code>
          </div>
          <p className="text-sm text-gray-400">
            Lumen support sessions & messages — often requires <code className="text-gray-300">X-AIF-Support-Token</code>{' '}
            once issued (see env <code className="text-gray-300">AIFACTORY_SUPPORT_REQUIRE_TOKEN</code>).
          </p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="info">ROUTER</Badge>
            <code className="text-sm text-white">/api/sandbox · /api/payment · /api/customer …</code>
          </div>
          <p className="text-sm text-gray-400">Sandbox previews, payments, feedback, marketing helpers — inspect Swagger for verbs.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="warning">PILOT</Badge>
            <code className="text-sm text-white">/ai-market/*</code>
          </div>
          <p className="text-sm text-gray-400">Separate AI-to-AI commerce pilot — not proxied as /api/ai-market.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="info">GET</Badge>
            <code className="text-sm text-white">/api/config/theme</code>
          </div>
          <p className="text-sm text-gray-400">Get current storefront theme configuration.</p>
        </GlassCard>

        <SubHeading>Admin Endpoints (JWT Required)</SubHeading>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="warning">POST</Badge>
            <code className="text-sm text-white">/api/admin/auth/login</code>
          </div>
          <p className="text-sm text-gray-400">
            Admin login. Sets HTTP-only cookie <code className="text-gray-300">access_token</code>; scripts may also send{' '}
            <code className="text-gray-300">Authorization: Bearer …</code>.
          </p>
          <CodeBlock code={`Request:
{
  "username": "admin",
  "password": "your_password",
  "totp_code": "123456"  // optional, if 2FA enabled
}

Response:
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "requires_2fa": false
}`} language="json" />
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/admin/dashboard</code>
          </div>
          <p className="text-sm text-gray-400">Dashboard metrics: pipeline stats, resources, revenue, security.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/admin/providers</code>
          </div>
          <p className="text-sm text-gray-400">List LLM providers with status, latency, and model info.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/admin/agents</code>
          </div>
          <p className="text-sm text-gray-400">List AI agents with status, tasks, and uptime.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/admin/security/logs?limit=100</code>
          </div>
          <p className="text-sm text-gray-400">Get audit logs with optional limit parameter.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="success">GET</Badge>
            <code className="text-sm text-white">/api/admin/director/reports</code>
          </div>
          <p className="text-sm text-gray-400">List Director AI generated reports.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="warning">POST</Badge>
            <code className="text-sm text-white">/api/admin/products/create</code>
          </div>
          <p className="text-sm text-gray-400">Create a new product from an idea.</p>
          <CodeBlock code={`Request:
{
  "idea": "Description of your product idea",
  "target_audience": "developers"  // optional
}`} language="json" />
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="warning">PATCH</Badge>
            <code className="text-sm text-white">/api/admin/pipeline/products/{'{id}'}/marketplace-copy</code>
          </div>
          <p className="text-sm text-gray-400">Merge storefront-facing marketing strings for a shipped product.</p>
        </GlassCard>

        <GlassCard className="p-4 my-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="warning">PATCH</Badge>
            <code className="text-sm text-white">/api/admin/pipeline/products/{'{id}'}/storefront-admin</code>
          </div>
          <p className="text-sm text-gray-400">Human score, force-list override, admin hide-from-storefront flags.</p>
        </GlassCard>
      </div>
    ),
  },
  {
    id: 'cli',
    title: 'CLI Commands',
    icon: Terminal,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          CLI <span className="text-gradient-primary">Commands</span>
        </h2>

        <Paragraph>
          Commands ship with the repo in <code className="text-cyan-400">cli/ai_company_cli.py</code>. Many README snippets use{' '}
          <code>ai-company</code> — prefer an explicit interpreter path unless your image aliases it.
        </Paragraph>

        <InfoBox title="Truth table" variant="warning">
          Some commands are demonstrations (wallet withdraw flow, parts of security scan). Read{' '}
          <code className="text-cyan-300">docs/cli-reference.md</code> before scripting automation.
        </InfoBox>

        <SubHeading>Invocation</SubHeading>
        <CodeBlock code={`docker compose exec app python /app/cli/ai_company_cli.py --help`} />

        <SubHeading>High-value operators</SubHeading>
        <CodeBlock code={`# First boot — writes admin.json + default YAML templates (password ≥12 chars)
docker compose exec -it app python /app/cli/ai_company_cli.py init

# Enqueue work
docker compose exec app python /app/cli/ai_company_cli.py create-idea "Landing for boutique coffee roasters"
docker compose exec app python /app/cli/ai_company_cli.py discover --top-k 5 --enqueue

# Providers & routing
docker compose exec app python /app/cli/ai_company_cli.py models list
docker compose exec app python /app/cli/ai_company_cli.py models test deepseek_api
docker compose exec app python /app/cli/ai_company_cli.py models switch code_generation local_ollama

# Director offline analysis
docker compose exec app python /app/cli/ai_company_cli.py director run-now
docker compose exec app python /app/cli/ai_company_cli.py director config

# Themes (reads/writes /app/config.yaml inside container)
docker compose exec app python /app/cli/ai_company_cli.py storefront list
docker compose exec app python /app/cli/ai_company_cli.py storefront apply cyberpunk

# Audit export
docker compose exec app python /app/cli/ai_company_cli.py audit export --from=2026-04-01 --format=json`} />

        <SubHeading>What is not implemented</SubHeading>
        <List items={[
          '`director report --last` — open Admin Director tab or read /app/data/reports/director/*.md',
          '`storefront preview` — use deployed Next.js or npm run dev inside web/frontend',
          '`restart web|orchestrator|director` — stub only; restart via Compose/systemd',
        ]} />

        <InfoBox title="Prefer Admin UI when…" variant="success">
          Editing LLM providers with hot reload, storefront hide/marketing panels, and Live Monitor are safer via /admin than hand-editing YAML unless you know the reload semantics.
        </InfoBox>
      </div>
    ),
  },
  {
    id: 'agents',
    title: 'AI Agents',
    icon: Bot,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          AI <span className="text-gradient-primary">Agents</span>
        </h2>

        <Paragraph>
          The platform uses ten core agents plus a Methodologist gate and the Evolution Analyst meta-agent, each with a
          strict role. Director AI sits above the loop. Agents communicate through the filesystem — no agent can modify
          another agent&apos;s work. For web deliverables, the Architect also emits <code className="text-cyan-300">ui_experience</code>
          (tokens, typography, motion) so the Developer ships intentional UI — shown as a dedicated <strong className="text-gray-200">Designer</strong> step on the public pipeline diagram.
        </Paragraph>

        <div className="space-y-4 my-6">
          {[
            { name: 'Analyst', role: 'Market research, opportunity analysis, research briefs', color: 'from-slate-500 to-indigo-500' },
            { name: 'PM (Product Manager)', role: 'Idea validation, market research, spec generation', color: 'from-indigo-500 to-purple-500' },
            {
              name: 'Methodologist',
              role: 'Domain process gate — verifies that the spec and the generated code follow the accepted methodology for the product domain (CRM, helpdesk, e-commerce, …) using pluggable domain packs and a learning store of operator lessons',
              color: 'from-sky-500 to-cyan-500',
            },
            { name: 'Architect', role: 'System design, technology stack decisions, architecture docs', color: 'from-purple-500 to-pink-500' },
            {
              name: 'Designer (UX layer)',
              role: 'Not a separate queue task: structured ui_experience (mood, CSS variables, fonts, motion, signature moment) authored with architecture and implemented by Developer',
              color: 'from-fuchsia-500 to-violet-500',
            },
            { name: 'Developer', role: 'Code implementation following architecture specs', color: 'from-orange-500 to-yellow-500' },
            { name: 'QA', role: 'Automated testing, bug detection, code quality analysis', color: 'from-emerald-500 to-teal-500' },
            { name: 'Security', role: 'Vulnerability scanning, secret detection, dependency audit', color: 'from-cyan-500 to-blue-500' },
            { name: 'DevOps', role: 'Dockerization, deployment config, sandbox setup', color: 'from-sky-500 to-indigo-500' },
            { name: 'Marketing', role: 'Product descriptions, landing pages, SEO content', color: 'from-pink-500 to-rose-500' },
            { name: 'Sales', role: 'Pricing, payment integration, customer interaction', color: 'from-amber-500 to-orange-500' },
            { name: 'Evolution Analyst', role: 'Telemetry analysis, auto-improvements, A/B testing', color: 'from-green-500 to-emerald-500' },
          ].map((agent) => {
            const CardIcon = agent.name.startsWith('Designer') ? Palette : Bot;
            return (
            <GlassCard key={agent.name} className="p-4">
              <div className="flex items-start gap-4">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${agent.color} p-2 flex-shrink-0`}>
                  <CardIcon className="w-full h-full text-white" />
                </div>
                <div>
                  <h4 className="text-white font-semibold">{agent.name}</h4>
                  <p className="text-sm text-gray-400">{agent.role}</p>
                </div>
              </div>
            </GlassCard>
            );
          })}
        </div>

        <SubHeading>Agent Safety</SubHeading>
        <List items={[
          'Strict role boundaries — no agent can perform another agent\'s tasks',
          'Timeout protection — agents have 30-second execution limit (configurable)',
          'Output validation — all agent outputs are validated against schemas',
          'Escalation — if an agent fails repeatedly, the Director AI is notified',
          'Filesystem-based memory — no context hallucination, all state is on disk',
        ]} />
      </div>
    ),
  },
  {
    id: 'pipeline',
    title: 'Pipeline Flow',
    icon: RefreshCw,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Pipeline <span className="text-gradient-primary">Flow</span>
        </h2>

        <Paragraph>
          The product lifecycle follows a deterministic state machine with 13 states.
          Each state is handled by a specific agent, ensuring clear ownership and accountability.
        </Paragraph>
        <Paragraph>
          Autonomous products still consume analyst/marketing idea flows; on-demand products anchor every downstream agent on the
          customer brief — <strong className="text-gray-200">not</strong> a separate lightweight conveyor for orders.
        </Paragraph>

        <SubHeading>Standard Pipeline</SubHeading>
        <GlassCard className="p-6 my-4">
          <div className="flex flex-wrap gap-2">
            {[
              'IDEA_RECEIVED',
              'SPEC_WRITTEN',
              'MARKET_CONTENT_READY',
              'METHODOLOGY_REVIEWED',
              'ARCH_DESIGNED',
              'CODE_COMMITTED',
              'QA_TESTING',
              'SECURITY_SCANNED',
              'SALES_ACTIVE',
              'SANDBOX_RUNNING',
              'TELEMETRY_COLLECTING',
              'EVOLUTION_ANALYZING',
            ].map((state, i, arr) => (
              <span key={state} className="flex items-center gap-1">
                <Badge variant="info">{state}</Badge>
                {i < arr.length - 1 && <ChevronRight className="w-4 h-4 text-gray-600" />}
              </span>
            ))}
          </div>
        </GlassCard>

        <SubHeading>Pipeline Features</SubHeading>
        <List items={[
          'Deterministic FSM — each product follows the same state machine',
          'Error recovery — if QA finds bugs, product loops back to DEV_FIXING',
          'Timeout management — each step has a configurable timeout (default 30s)',
          'Parallel execution — multiple products can be in different pipeline stages',
          'State persistence — JSON (default) or optional SQLite3 backend with CLI migration',
          'Director override — Director AI can adjust timeouts and priorities',
        ]} />

        <SubHeading>Director AI Cycle (Every 4 Hours)</SubHeading>
        <Paragraph>
          In parallel with the product pipeline, the Director AI runs every 4 hours:
        </Paragraph>
        <List items={[
          '1. Collect metrics from all sources (state files, telemetry, logs, database)',
          '2. Analyze metrics against target values, identify anomalies and trends',
          '3. Generate decisions — auto-apply allowed actions, queue recommendations for admin',
          '4. Generate markdown report saved to /data/reports/director/',
          '5. Notify admin panel with ready report',
        ]} />
      </div>
    ),
  },
  {
    id: 'crypto',
    title: 'Crypto Payments',
    icon: DollarSign,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Crypto <span className="text-gradient-primary">Payments</span>
        </h2>

        <Paragraph>
          AI-Factory supports multi-chain crypto payments for generated products.
          Customers can purchase products using USDT or USDC stablecoins.
        </Paragraph>
        <InfoBox title="Economics" variant="info">
          Storefront and checkout default to about <strong className="text-gray-200">$4.99 USDT</strong> when marketing/sales
          files do not specify another price — tuned for impulse landing purchases while operators override per SKU.
        </InfoBox>

        <SubHeading>Supported Networks</SubHeading>
        <div className="grid md:grid-cols-3 gap-4 my-4">
          {[
            { name: 'Base', tokens: 'USDT, USDC', icon: Coins },
            { name: 'Solana', tokens: 'USDT, USDC', icon: Coins },
            { name: 'Arbitrum', tokens: 'USDT, USDC', icon: Coins },
          ].map((chain) => (
            <GlassCard key={chain.name} className="p-4 text-center">
              <Coins className="w-8 h-8 text-yellow-400 mx-auto mb-2" />
              <h4 className="text-white font-semibold">{chain.name}</h4>
              <p className="text-xs text-gray-500">{chain.tokens}</p>
            </GlassCard>
          ))}
        </div>

        <SubHeading>Payment Flow</SubHeading>
        <List items={[
          'Customer selects product and chooses a network (Base/Solana/Arbitrum)',
          'System generates a unique payment address and amount',
          'Customer sends USDT/USDC to the provided address',
          'System monitors blockchain confirmations (polling every 15s)',
          'On sufficient confirmations — product license is activated',
          'Customer gains access to sandbox demo and full product',
        ]} />

        <SubHeading>Wallet Management</SubHeading>
        <Paragraph>
          Platform wallets are configured via the CLI. Wallet addresses are displayed in the admin panel
          under Crypto Settings. Withdrawals require multi-signature approval.
        </Paragraph>
      </div>
    ),
  },
  {
    id: 'security',
    title: 'Security',
    icon: Shield,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          <span className="text-gradient-primary">Security</span>
        </h2>

        <Paragraph>
          AI-Factory implements enterprise-grade security measures across all layers.
        </Paragraph>

        <SubHeading>Authentication & Authorization</SubHeading>
        <List items={[
          'JWT-based authentication with HTTP-only cookies',
          'Password hashing with SHA-256 + salt (fallback)',
          '2FA support via Google Authenticator (TOTP)',
          'Brute-force protection: 5 failed attempts max per 15 minutes',
          '30-minute session inactivity timeout',
          'All admin actions logged to tamper-evident audit log',
        ]} />

        <SubHeading>Sandbox Isolation</SubHeading>
        <List items={[
          'Docker-in-Docker for product sandboxes',
          'No network access from sandboxes (default)',
          'Resource limits (CPU/memory) per sandbox',
          'Filesystem isolation — no access to host files',
          'Automatic sandbox cleanup on timeout',
        ]} />

        <SubHeading>Data Protection</SubHeading>
        <List items={[
          'Secrets encrypted at rest using Fernet (symmetric encryption)',
          'Audit logs are append-only with tamper detection',
          'Rate limiting on all API endpoints',
          'No sensitive data returned in API responses',
          'Firewall rules within container (nftables)',
        ]} />

        <SubHeading>Security Monitoring</SubHeading>
        <List items={[
          'Real-time security dashboard in admin panel',
          'Failed login attempt tracking with IP logging',
          'Audit log export in JSON format',
          'Automatic alerts on suspicious activity',
        ]} />

        <InfoBox title="Default Credentials" variant="warning">
          Default password is <code>admin123</code>. Change it immediately after first login via the
          Settings tab in the admin panel.
        </InfoBox>
      </div>
    ),
  },
  {
    id: 'director',
    title: 'Director AI',
    icon: BarChart3,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          Director <span className="text-gradient-primary">AI</span>
        </h2>

        <Paragraph>
          The Director AI is a meta-agent that oversees the entire platform. It does not participate in
          product development but evaluates system performance and makes optimization decisions.
        </Paragraph>

        <SubHeading>Analysis Cycle (Every 4 Hours)</SubHeading>
        <List items={[
          '1. Metrics Collection — gathers data from pipeline state, telemetry, logs, and financial records',
          '2. Analysis — compares metrics against targets, identifies anomalies and trends',
          '3. Decision Making — generates automatic actions (if enabled) and recommendations',
          '4. Report Generation — creates detailed markdown report',
          '5. Notification — updates admin panel with new report',
        ]} />

        <SubHeading>Metrics Tracked</SubHeading>

        <div className="grid md:grid-cols-2 gap-4 my-4">
          <GlassCard className="p-4">
            <h4 className="text-white font-semibold mb-2">Pipeline Efficiency</h4>
            <ul className="text-sm text-gray-400 space-y-1">
              <li>{'•'} Idea → MVP time (target: {'<'}4h)</li>
              <li>{'•'} Auto-completion rate (target: {'>'}95%)</li>
              <li>{'•'} Agent timeout/error rates</li>
              <li>{'•'} Auto-fix success rate (target: {'>'}85%)</li>
            </ul>
          </GlassCard>
          <GlassCard className="p-4">
            <h4 className="text-white font-semibold mb-2">Business Metrics</h4>
            <ul className="text-sm text-gray-400 space-y-1">
              <li>• Sandbox → purchase conversion (target: {'>'}12%)</li>
              <li>• Average order value in crypto</li>
              <li>• Top/bottom products by revenue</li>
              <li>• Marketing content effectiveness</li>
            </ul>
          </GlassCard>
          <GlassCard className="p-4">
            <h4 className="text-white font-semibold mb-2">Technical Health</h4>
            <ul className="text-sm text-gray-400 space-y-1">
              <li>• CPU/RAM/disk usage alerts</li>
              <li>• LLM provider availability</li>
              <li>• Security incident count</li>
              <li>• Model inference latency (P95)</li>
            </ul>
          </GlassCard>
          <GlassCard className="p-4">
            <h4 className="text-white font-semibold mb-2">Product Quality</h4>
            <ul className="text-sm text-gray-400 space-y-1">
              <li>• Average product rating (from reviews)</li>
              <li>• Bugs per 1000 lines of code</li>
              <li>• Critical bug response time (P0)</li>
              <li>• Evolution improvements applied</li>
            </ul>
          </GlassCard>
        </div>

        <SubHeading>Automatic Actions</SubHeading>
        <Paragraph>
          When enabled, the Director AI can automatically:
        </Paragraph>
        <List items={[
          'Increase agent timeouts if timeout rate exceeds 15%',
          'Trigger marketing reviews if conversion drops below 8%',
          'Recommend switching to local models if GPU is underutilized',
          'Adjust resource limits based on usage patterns',
        ]} />

        <SubHeading>Report Format</SubHeading>
        <Paragraph>
          Director reports are saved as Markdown files in <code>/data/reports/director/</code> and displayed
          in the admin panel. Each report includes:
        </Paragraph>
        <List items={[
          'Key metrics comparison (actual vs target)',
          'Automatic actions applied',
          'Recommendations requiring admin approval',
          '24-hour forecast with risk assessment',
        ]} />
      </div>
    ),
  },
  {
    id: 'configuration',
    title: 'Configuration',
    icon: FileText,
    content: (
      <div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">
          <span className="text-gradient-primary">Configuration</span>
        </h2>

        <Paragraph>
          The platform is configured through YAML and JSON files in <code>/data/config/</code>.
          Changes can be made via the admin panel or directly by editing these files.
        </Paragraph>

        <SubHeading>Model Providers (<code>model_providers.yaml</code>)</SubHeading>
        <CodeBlock code={`providers:
  local_ollama:
    enabled: true
    base_url: "http://host.docker.internal:11434"
    models:
      heavy: "qwen3.6-35b-a3b"
      light: "qwen2.5-7b"
      vision: "llava-llama3"

  deepseek_api:
    enabled: false
    api_key_env: "DEEPSEEK_API_KEY"
    base_url: "https://api.deepseek.com/v1"
    models:
      heavy: "deepseek-chat"
      light: "deepseek-coder"
    fallback: "local_ollama"`} language="yaml" />

        <SubHeading>Routing Rules</SubHeading>
        <CodeBlock code={`routing_rules:
  - task_type: "architecture_design"
    preferred_provider: "local_ollama"
    model_role: "heavy"
    timeout_sec: 120

  - task_type: "marketing_copy"
    preferred_provider: "auto"
    model_role: "light"
    timeout_sec: 30

  - task_type: "code_generation"
    preferred_provider: "local_ollama"
    model_role: "heavy"
    fallback_provider: "deepseek_api"`} language="yaml" />

        <SubHeading>Global Config (<code>config.yaml</code>)</SubHeading>
        <CodeBlock code={`# Global platform settings
orchestrator:
  default_timeout_sec: 30
  max_retries: 3
  pipeline_interval_sec: 5

director:
  analysis_interval_hours: 4
  auto_actions_enabled: true
  max_reports_retention: 30

security:
  max_login_attempts: 5
  login_window_minutes: 15
  session_timeout_minutes: 30

storefront:
  default_theme: "cyberpunk"
  animation_enabled: true`} language="yaml" />

        <SubHeading>Themes</SubHeading>
        <Paragraph>
          Five pre-installed themes are available:
        </Paragraph>
        <List items={[
          'Cyberpunk — neon cyan, purple accents, dark gradient background',
          'Minimal — clean white/gray with subtle shadows',
          'Glass — transparent panels with heavy blur effects',
          'Neon — bright neon colors on dark background',
          'Corporate — professional blue/white color scheme',
        ]} />
      </div>
    ),
  },
];

// ── Docs Page ─────────────────────────────────────────────────────────────

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState('overview');

  const currentDoc = docSections.find((s) => s.id === activeSection) || docSections[0];

  return (
    <div className="min-h-screen">
      <DocNavbar />

      {/* Hero */}
      <section className="relative pt-20 pb-12 px-4">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 left-1/3 w-64 h-64 bg-indigo-500/10 rounded-full blur-[100px]" />
        </div>
        <div className="relative max-w-7xl mx-auto">
          <a
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </a>
          <div className="flex items-center gap-3 mb-2">
            <BookOpen className="w-8 h-8 text-indigo-400" />
            <h1 className="text-4xl md:text-5xl font-bold">
              <span className="text-gradient">Documentation</span>
            </h1>
          </div>
          <p className="text-gray-400 text-lg max-w-2xl">
            Architecture, quick start, owner playbook with visuals, API reference, CLI truth table, and links to the Markdown
            handbooks in <code className="text-gray-500">docs/</code>.
          </p>
        </div>
      </section>

      {/* Content */}
      <section className="pb-24 px-4">
        <div className="max-w-7xl mx-auto flex gap-8">
          {/* Sidebar */}
          <DocSidebar
            sections={docSections}
            activeSection={activeSection}
            onSectionChange={setActiveSection}
          />

          {/* Mobile Section Selector */}
          <div className="lg:hidden w-full mb-6">
            <select
              value={activeSection}
              onChange={(e) => setActiveSection(e.target.value)}
              className="w-full glass-card p-3 text-white bg-transparent border border-white/10 rounded-xl text-sm"
            >
              {docSections.map((section) => (
                <option key={section.id} value={section.id} className="bg-gray-900">
                  {section.title}
                </option>
              ))}
            </select>
          </div>

          {/* Main Content */}
          <motion.div
            key={activeSection}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="flex-1 min-w-0"
          >
            <div className="max-w-4xl">
              {currentDoc.content}
            </div>

            {/* Navigation between sections */}
            <div className="flex items-center justify-between mt-12 pt-8 border-t border-white/5">
              <div>
                {docSections.findIndex((s) => s.id === activeSection) > 0 && (
                  <button
                    onClick={() => {
                      const idx = docSections.findIndex((s) => s.id === activeSection);
                      setActiveSection(docSections[idx - 1].id);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    {docSections[docSections.findIndex((s) => s.id === activeSection) - 1]?.title}
                  </button>
                )}
              </div>
              <div>
                {docSections.findIndex((s) => s.id === activeSection) < docSections.length - 1 && (
                  <button
                    onClick={() => {
                      const idx = docSections.findIndex((s) => s.id === activeSection);
                      setActiveSection(docSections[idx + 1].id);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    {docSections[docSections.findIndex((s) => s.id === activeSection) + 1]?.title}
                    <ChevronRight className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8 px-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <span className="text-sm text-gray-400">AI-Factory v2.1 — Documentation</span>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
            <a href="/" className="hover:text-gray-300 transition-colors">Home</a>
            <a href="/admin" className="hover:text-gray-300 transition-colors">Admin</a>
            <a href="/api/docs" className="hover:text-gray-300 transition-colors">API Docs</a>
            <a
              href="https://github.com/alexar76/aicom"
              className="hover:text-gray-300 transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
