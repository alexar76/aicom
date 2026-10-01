import React from 'react';
import {
  BookOpen,
  GraduationCap,
  Crown,
  Server,
  Zap,
  Settings,
  Code2,
  Terminal,
  Bot,
  RefreshCw,
  DollarSign,
  Shield,
  BarChart3,
  FileText,
  Workflow,
  ChevronRight,
  Coins,
  Palette,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Badge } from '@/components/ui/Badge';
import type { DocsStrings } from '@/lib/docs-i18n/types';

export interface DocSection {
  id: string;
  title: string;
  icon: React.ElementType;
  content: React.ReactNode;
}

type CodeBlockProps = { code: string; language?: string };
type InfoBoxProps = {
  title: string;
  children: React.ReactNode;
  variant?: 'info' | 'warning' | 'success';
};
type DocScreenshotProps = { src: string; caption: string };
type SubHeadingProps = { children: React.ReactNode };
type ParagraphProps = { children: React.ReactNode };
type ListProps = { items: React.ReactNode[] };

export type DocsSectionUi = {
  CodeBlock: React.ComponentType<CodeBlockProps>;
  InfoBox: React.ComponentType<InfoBoxProps>;
  DocScreenshot: React.ComponentType<DocScreenshotProps>;
  SubHeading: React.ComponentType<SubHeadingProps>;
  Paragraph: React.ComponentType<ParagraphProps>;
  List: React.ComponentType<ListProps>;
};

const AGENT_GRADIENTS: Record<string, string> = {
  Analyst: 'from-slate-500 to-indigo-500',
  'PM (Product Manager)': 'from-indigo-500 to-purple-500',
  Methodologist: 'from-sky-500 to-cyan-500',
  Architect: 'from-purple-500 to-pink-500',
  'Designer (UX layer)': 'from-fuchsia-500 to-violet-500',
  Developer: 'from-orange-500 to-yellow-500',
  QA: 'from-emerald-500 to-teal-500',
  Security: 'from-cyan-500 to-blue-500',
  DevOps: 'from-sky-500 to-indigo-500',
  Marketing: 'from-pink-500 to-rose-500',
  Sales: 'from-amber-500 to-orange-500',
  'Evolution Analyst': 'from-green-500 to-emerald-500',
};

const ENDPOINT_BADGE_VARIANT: Record<string, 'success' | 'warning' | 'info'> = {
  GET: 'success',
  POST: 'warning',
  PATCH: 'warning',
  MIXED: 'success',
  ROUTER: 'info',
  PROTOCOL: 'warning',
};

const NEXT_CONFIG_REWRITE = `next.config.js:
// All /api/* requests are proxied to FastAPI backend
async rewrites() {
  return [
    { source: '/api/:path*', destination: 'http://localhost:8081/api/:path*' },
  ];
}`;

const DOCKER_BUILD = `docker build -t ai-factory .`;

const DOCKER_RUN = `docker run -d \\
  --name ai-factory \\
  -v ./data:/app/data \\
  -p 8080:8080 \\
  ai-factory`;

const FIRST_PRODUCT_CLI = `# Via CLI
docker exec -it ai-factory python cli/ai_company_cli.py create-idea "Your product idea here"

# Or via Admin Panel
# Go to /admin → New Product tab → Submit idea`;

const CLI_INVOCATION = `docker compose exec app python /app/cli/ai_company_cli.py --help`;

const CLI_HIGH_VALUE = `# First boot — writes admin.json + default YAML templates (password ≥12 chars)
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
docker compose exec app python /app/cli/ai_company_cli.py audit export --from=2026-04-01 --format=json`;

const MODEL_PROVIDERS_YAML = `providers:
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
    fallback: "local_ollama"`;

const ROUTING_RULES_YAML = `routing_rules:
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
    fallback_provider: "deepseek_api"`;

const GLOBAL_CONFIG_YAML = `# Global platform settings
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
  animation_enabled: true`;

function endpointBadgeVariant(method: string): 'success' | 'warning' | 'info' {
  return ENDPOINT_BADGE_VARIANT[method] ?? 'info';
}

function ApiEndpointCard({
  method,
  path,
  description,
  code,
  codeLanguage,
  CodeBlock,
}: {
  method: string;
  path: string;
  description: string;
  code?: string;
  codeLanguage?: string;
  CodeBlock: DocsSectionUi['CodeBlock'];
}) {
  return (
    <GlassCard className="p-4 my-3">
      <div className="flex items-center gap-3 mb-2">
        <Badge variant={endpointBadgeVariant(method)}>{method}</Badge>
        <code className="text-sm text-white">{path}</code>
      </div>
      <p className="text-sm text-gray-400">{description}</p>
      {code ? <CodeBlock code={code} language={codeLanguage} /> : null}
    </GlassCard>
  );
}

export function buildDocSections(t: DocsStrings, ui: DocsSectionUi): DocSection[] {
  const { CodeBlock, InfoBox, DocScreenshot, SubHeading, Paragraph, List } = ui;
  const st = t.sectionTitles;
  const ep = t.apiReference.endpoints;
  return [
    {
      id: 'overview',
      title: st.overview,
      icon: BookOpen,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-gradient">{t.overview.title}</span>
          </h2>
          <Badge variant="info" className="mb-6">{t.overview.badge}</Badge>
          <Paragraph>
            {t.overview.intro}{' '}
            <strong className="text-gray-200">{t.overview.introPipeline}</strong>
            {t.overview.introPipelineSuffix}{' '}
            <strong className="text-gray-200">{t.overview.introAutonomous}</strong>
            {t.overview.introAutonomousSuffix}{' '}
            <strong className="text-gray-200">{t.overview.introOnDemand}</strong>
            {t.overview.introOnDemandSuffix} {t.overview.introEnd}
          </Paragraph>
          <SubHeading>{t.overview.coreCapabilities}</SubHeading>
          <List items={t.overview.capabilities} />
          <SubHeading>{t.overview.atAGlance}</SubHeading>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 my-4">
            {t.overview.stats.map((stat) => (
              <div key={stat.label} className="glass-card p-4 text-center">
                <div className="text-2xl font-bold text-white">{stat.value}</div>
                <div className="text-xs text-gray-500 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
          <InfoBox title={t.overview.singleContainerTitle} variant="info">{t.overview.singleContainerBody}</InfoBox>
          <InfoBox title={t.overview.handbookTitle} variant="success">
            {t.overview.handbookBodyPrefix}
            <code className="text-cyan-300">{t.overview.handbookBodyPath}</code>
            {t.overview.handbookBodySuffix}
          </InfoBox>
          <InfoBox title={t.overview.userGuideBoxTitle} variant="info">
            {t.overview.userGuideBoxPrefix}
            <code className="text-cyan-300">{t.overview.userGuideBoxPath}</code>
            <span className="font-medium text-gray-200">{t.overview.userGuideBoxTab}</span>
            {t.overview.userGuideBoxSuffix}
            <code className="text-cyan-300">{t.overview.userGuideBoxDocsPath}</code>.
          </InfoBox>
        </div>
      ),
    },
    {
      id: 'user-guide',
      title: st.userGuide,
      icon: GraduationCap,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4 flex items-center gap-3">
            <GraduationCap className="w-9 h-9 text-emerald-400" />
            <span>
              {t.userGuide.titlePrefix}
              <span className="text-gradient-primary">{t.userGuide.titleGradient}</span>
            </span>
          </h2>
          <Badge variant="info" className="mb-6">{t.userGuide.badge}</Badge>
          <Paragraph>{t.userGuide.intro}</Paragraph>
          <SubHeading>{t.userGuide.whatYouWillLearnTitle}</SubHeading>
          <List items={t.userGuide.whatYouWillLearnItems} />
          <SubHeading>{t.userGuide.screenshotsTitle}</SubHeading>
          <Paragraph>{t.userGuide.screenshotsRegenerate}</Paragraph>
          <DocScreenshot src="/docs-screenshots/public-home.png" caption={t.userGuide.captions.publicHome} />
          <DocScreenshot src="/docs-screenshots/public-docs.png" caption={t.userGuide.captions.publicDocs} />
          <DocScreenshot src="/docs-screenshots/admin-new-product.png" caption={t.userGuide.captions.adminNewProduct} />
          <DocScreenshot src="/docs-screenshots/admin-workshop.png" caption={t.userGuide.captions.adminWorkshop} />
          <DocScreenshot src="/docs-screenshots/admin-pipeline.png" caption={t.userGuide.captions.adminPipeline} />
          <InfoBox title={t.userGuide.offlineTitle} variant="warning">
            {t.userGuide.offlineBodyPrefix}
            <code className="text-cyan-300">{t.userGuide.offlineBodyPath1}</code>
            {t.userGuide.offlineBodyMiddle}
            <code className="text-cyan-300">{t.userGuide.offlineBodyPath2}</code>.
          </InfoBox>
        </div>
      ),
    },

    {
      id: 'owner-guide',
      title: st.ownerGuide,
      icon: Crown,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4 flex items-center gap-3">
            <Crown className="w-9 h-9 text-amber-400" />
            <span>
              {t.ownerGuide.titlePrefix}
              <span className="text-gradient-primary">{t.ownerGuide.titleGradient}</span>
            </span>
          </h2>
          <Badge variant="info" className="mb-6">{t.ownerGuide.badge}</Badge>
          <Paragraph>{t.ownerGuide.intro}</Paragraph>
          <SubHeading>{t.ownerGuide.visualMapTitle}</SubHeading>
          <GlassCard className="p-6 my-4 overflow-x-auto">
            <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm mb-4">
              <Workflow className="w-5 h-5" />
              {t.ownerGuide.operatorControlPlane}
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
          <SubHeading>{t.ownerGuide.firstDayTitle}</SubHeading>
          <List items={t.ownerGuide.firstDayItems} />
          <SubHeading>{t.ownerGuide.marketplaceTitle}</SubHeading>
          <List items={t.ownerGuide.marketplaceItems} />
          <div className="grid md:grid-cols-2 gap-4 my-4">
            {t.ownerGuide.useCaseCards.map((card) => (
              <GlassCard key={card.title} className="p-4 border border-white/10">
                <h4 className="text-white font-semibold mb-2">{card.title}</h4>
                <p className="text-sm text-gray-400 leading-relaxed">{card.body}</p>
              </GlassCard>
            ))}
          </div>
          <SubHeading>{t.ownerGuide.listingFlowTitle}</SubHeading>
          <GlassCard className="p-6 my-4 font-mono text-[13px] text-gray-300 leading-relaxed">
            <div className="text-cyan-400 mb-2">{t.ownerGuide.listingShippedQuestion}</div>
            <div className="pl-4 border-l border-white/10 mb-2">
              {t.ownerGuide.listingShippedNo}
            </div>
            <div className="text-cyan-400 mb-2">{t.ownerGuide.listingHiddenQuestion}</div>
            <div className="pl-4 border-l border-white/10 mb-2">
              {t.ownerGuide.listingHiddenYes}
            </div>
            <div className="text-cyan-400 mb-2">{t.ownerGuide.listingQualityQuestion}</div>
            <div className="pl-4 border-l border-white/10">{t.ownerGuide.listingQualityYes}</div>
          </GlassCard>
          <SubHeading>{t.ownerGuide.screenshotsTitle}</SubHeading>
          <Paragraph>{t.ownerGuide.screenshotsIntro}</Paragraph>
          <DocScreenshot src="/docs-screenshots/admin-login.png" caption={t.ownerGuide.captions.adminLogin} />
          <DocScreenshot src="/docs-screenshots/admin-dashboard.png" caption={t.ownerGuide.captions.adminDashboard} />
          <DocScreenshot src="/docs-screenshots/admin-pipeline.png" caption={t.ownerGuide.captions.adminPipeline} />
          <DocScreenshot src="/docs-screenshots/admin-new-product.png" caption={t.ownerGuide.captions.adminNewProduct} />
          <DocScreenshot src="/docs-screenshots/admin-workshop.png" caption={t.ownerGuide.captions.adminWorkshop} />
          <DocScreenshot src="/docs-screenshots/admin-providers.png" caption={t.ownerGuide.captions.adminProviders} />
          <DocScreenshot src="/docs-screenshots/admin-settings.png" caption={t.ownerGuide.captions.adminSettings} />
          <InfoBox title={t.ownerGuide.mermaidTitle} variant="info">
            {t.ownerGuide.mermaidBodyPrefix}
            <code className="text-cyan-300">{t.ownerGuide.mermaidBodyPath}</code>
            {t.ownerGuide.mermaidBodySuffix}
          </InfoBox>
        </div>
      ),
    },

    {
      id: 'architecture',
      title: st.architecture,
      icon: Server,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            System <span className="text-gradient-primary">{t.architecture.titleGradient}</span>
          </h2>
          <Paragraph>{t.architecture.intro}</Paragraph>
          <SubHeading>{t.architecture.componentDiagramTitle}</SubHeading>
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
          <SubHeading>{t.architecture.requestFlow}</SubHeading>
          <Paragraph>{t.architecture.requestFlowBody}</Paragraph>
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
      title: st.quickstart,
      icon: Zap,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Quick <span className="text-gradient-primary">{t.quickstart.titleGradient}</span>
          </h2>
          <Paragraph>{t.quickstart.intro}</Paragraph>
          <SubHeading>{t.quickstart.step1}</SubHeading>
          <CodeBlock code="docker build -t ai-factory ." />
          <SubHeading>{t.quickstart.step2}</SubHeading>
          <CodeBlock code={`docker run -d \\
  --name ai-factory \\
  -v ./data:/app/data \\
  -p 8080:8080 \\
  ai-factory`} />
          <SubHeading>{t.quickstart.step3}</SubHeading>
          <List
            items={t.quickstart.accessLinks.map((link) => (
              <span key={link.label}>
                {link.label}:{' '}
                <a href={link.url} className="text-indigo-400 hover:underline">
                  {link.url}
                </a>
                {link.note ? ` (${link.note})` : ''}
              </span>
            ))}
          />
          <SubHeading>{t.quickstart.step4}</SubHeading>
          <Paragraph>{t.quickstart.loginIntro}</Paragraph>
          <List items={t.quickstart.loginItems} />
          <SubHeading>{t.quickstart.step5}</SubHeading>
          <CodeBlock code={`# Via CLI
docker exec -it ai-factory python cli/ai_company_cli.py create-idea "Your product idea here"

# Or via Admin Panel
# Go to /admin → New Product tab → Submit idea`} />
          <InfoBox title={t.quickstart.dockerSandboxTitle} variant="info">
            {t.quickstart.dockerSandboxBody}
          </InfoBox>
        </div>
      ),
    },
    {
      id: 'admin-panel',
      title: st.adminPanel,
      icon: Settings,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Admin <span className="text-gradient-primary">{t.adminPanel.titleGradient}</span>
          </h2>
          <Paragraph>{t.adminPanel.intro}</Paragraph>
          <SubHeading>{t.adminPanel.authTitle}</SubHeading>
          <List items={t.adminPanel.authItems} />
          <SubHeading>{t.adminPanel.dashboardTitle}</SubHeading>
          <Paragraph>{t.adminPanel.dashboardIntro}</Paragraph>
          <List items={t.adminPanel.dashboardItems} />
          <SubHeading>{t.adminPanel.providersTitle}</SubHeading>
          <Paragraph>{t.adminPanel.providersIntro}</Paragraph>
          <List items={t.adminPanel.providersItems} />
          <SubHeading>{t.adminPanel.agentsTitle}</SubHeading>
          <Paragraph>{t.adminPanel.agentsIntro}</Paragraph>
          <List items={t.adminPanel.agentsItems} />
          <SubHeading>{t.adminPanel.securityTitle}</SubHeading>
          <Paragraph>{t.adminPanel.securityIntro}</Paragraph>
          <List items={t.adminPanel.securityItems} />
          <SubHeading>{t.adminPanel.directorTitle}</SubHeading>
          <Paragraph>{t.adminPanel.directorIntro}</Paragraph>
          <List items={t.adminPanel.directorItems} />
          <SubHeading>{t.adminPanel.settingsTitle}</SubHeading>
          <Paragraph>{t.adminPanel.settingsIntro}</Paragraph>
          <List items={t.adminPanel.settingsItems} />
        </div>
      ),
    },

    {
      id: 'api-reference',
      title: st.apiReference,
      icon: Code2,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            API <span className="text-gradient-primary">{t.apiReference.titleGradient}</span>
          </h2>
          <Paragraph>
            {t.apiReference.intro.split(t.apiReference.introSwagger)[0]}
            <a href={t.apiReference.introSwagger} className="text-indigo-400 hover:underline">
              {t.apiReference.introSwagger}
            </a>
            {t.apiReference.intro.split(t.apiReference.introSwagger)[1]}
          </Paragraph>
          <InfoBox title={t.apiReference.handbookTitle} variant="info">
            {t.apiReference.handbookBodyPrefix}
            <code className="text-cyan-300">{t.apiReference.handbookBodyPath}</code>
            {t.apiReference.handbookBodySuffix}
          </InfoBox>
          <SubHeading>{t.apiReference.publicEndpoints}</SubHeading>
          <ApiEndpointCard method={ep.health.method} path={ep.health.path} description={ep.health.description} code={ep.health.code} codeLanguage={ep.health.codeLanguage} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.products.method} path={ep.products.path} description={ep.products.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.productById.method} path="/api/products/{'{id}'}" description={ep.productById.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.support.method} path={ep.support.path} description={ep.support.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.sandboxRouter.method} path={ep.sandboxRouter.path} description={ep.sandboxRouter.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.aiMarket.method} path={ep.aiMarket.path} description={ep.aiMarket.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.theme.method} path={ep.theme.path} description={ep.theme.description} CodeBlock={CodeBlock} />
          <SubHeading>{t.apiReference.adminEndpoints}</SubHeading>
          <ApiEndpointCard method={ep.adminLogin.method} path={ep.adminLogin.path} description={ep.adminLogin.description} code={ep.adminLogin.code} codeLanguage={ep.adminLogin.codeLanguage} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminDashboard.method} path={ep.adminDashboard.path} description={ep.adminDashboard.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminProviders.method} path={ep.adminProviders.path} description={ep.adminProviders.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminAgents.method} path={ep.adminAgents.path} description={ep.adminAgents.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminSecurityLogs.method} path={ep.adminSecurityLogs.path} description={ep.adminSecurityLogs.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminDirectorReports.method} path={ep.adminDirectorReports.path} description={ep.adminDirectorReports.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminProductsCreate.method} path={ep.adminProductsCreate.path} description={ep.adminProductsCreate.description} code={ep.adminProductsCreate.code} codeLanguage={ep.adminProductsCreate.codeLanguage} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminMarketplaceCopy.method} path="/api/admin/pipeline/products/{'{id}'}/marketplace-copy" description={ep.adminMarketplaceCopy.description} CodeBlock={CodeBlock} />
          <ApiEndpointCard method={ep.adminStorefrontAdmin.method} path="/api/admin/pipeline/products/{'{id}'}/storefront-admin" description={ep.adminStorefrontAdmin.description} CodeBlock={CodeBlock} />
        </div>
      ),
    },
    {
      id: 'cli',
      title: st.cli,
      icon: Terminal,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            CLI <span className="text-gradient-primary">{t.cli.titleGradient}</span>
          </h2>
          <Paragraph>{t.cli.intro}</Paragraph>
          <InfoBox title={t.cli.truthTableTitle} variant="warning">
            {t.cli.truthTableBodyPrefix}
            <code className="text-cyan-300">{t.cli.truthTableBodyPath}</code>
          </InfoBox>
          <SubHeading>{t.cli.invocationTitle}</SubHeading>
          <CodeBlock code="docker compose exec app python /app/cli/ai_company_cli.py --help" />
          <SubHeading>{t.cli.highValueTitle}</SubHeading>
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
          <SubHeading>{t.cli.notImplementedTitle}</SubHeading>
          <List items={t.cli.notImplementedItems} />
          <InfoBox title={t.cli.preferAdminTitle} variant="success">
            {t.cli.preferAdminBody}
          </InfoBox>
        </div>
      ),
    },

    {
      id: 'agents',
      title: st.agents,
      icon: Bot,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            AI <span className="text-gradient-primary">{t.agents.titleGradient}</span>
          </h2>
          <Paragraph>
            {t.agents.intro}
            <strong className="text-gray-200">{t.agents.introDesigner}</strong>
            {t.agents.introSuffix}
          </Paragraph>
          <div className="space-y-4 my-6">
            {t.agents.cards.map((agent, index) => {
              const CardIcon = agent.name.startsWith('Designer') ? Palette : Bot;
              return (
                <GlassCard key={agent.name} className="p-4">
                  <div className="flex items-start gap-4">
                    <div
                      className={`w-10 h-10 rounded-xl bg-gradient-to-br ${AGENT_GRADIENTS[agent.name] ?? 'from-slate-500 to-indigo-500'} p-2 flex-shrink-0`}
                    >
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
          <SubHeading>{t.agents.safety}</SubHeading>
          <List items={t.agents.safetyItems} />
        </div>
      ),
    },
    {
      id: 'pipeline',
      title: st.pipeline,
      icon: RefreshCw,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Pipeline <span className="text-gradient-primary">{t.pipeline.titleGradient}</span>
          </h2>
          <Paragraph>{t.pipeline.intro}</Paragraph>
          <Paragraph>{t.pipeline.introOnDemand}</Paragraph>
          <SubHeading>{t.pipeline.standardPipeline}</SubHeading>
          <GlassCard className="p-6 my-4">
            <div className="flex flex-wrap gap-2">
              {t.pipeline.pipelineStates.map((state, i, arr) => (
                <span key={state} className="flex items-center gap-1">
                  <Badge variant="info">{state}</Badge>
                  {i < arr.length - 1 && <ChevronRight className="w-4 h-4 text-gray-600" />}
                </span>
              ))}
            </div>
          </GlassCard>
          <SubHeading>{t.pipeline.featuresTitle}</SubHeading>
          <List items={t.pipeline.featuresItems} />
          <SubHeading>{t.pipeline.directorCycleTitle}</SubHeading>
          <Paragraph>{t.pipeline.directorCycleIntro}</Paragraph>
          <List items={t.pipeline.directorCycleItems} />
        </div>
      ),
    },

    {
      id: 'crypto',
      title: st.crypto,
      icon: DollarSign,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Crypto <span className="text-gradient-primary">{t.crypto.titleGradient}</span>
          </h2>
          <Paragraph>{t.crypto.intro}</Paragraph>
          <InfoBox title={t.crypto.economicsTitle} variant="info">
            {t.crypto.economicsBody}
          </InfoBox>
          <SubHeading>{t.crypto.supportedNetworks}</SubHeading>
          <div className="grid md:grid-cols-3 gap-4 my-4">
            {t.crypto.chains.map((chain) => (
              <GlassCard key={chain.name} className="p-4 text-center">
                <Coins className="w-8 h-8 text-yellow-400 mx-auto mb-2" />
                <h4 className="text-white font-semibold">{chain.name}</h4>
                <p className="text-xs text-gray-500">{chain.tokens}</p>
              </GlassCard>
            ))}
          </div>
          <SubHeading>{t.crypto.paymentFlowTitle}</SubHeading>
          <List items={t.crypto.paymentFlowItems} />
          <SubHeading>{t.crypto.walletTitle}</SubHeading>
          <Paragraph>{t.crypto.walletBody}</Paragraph>
        </div>
      ),
    },
    {
      id: 'uni-credit',
      title: st.uniCredit,
      icon: Coins,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            UNI <span className="text-gradient-primary">{t.uniCredit.titleGradient}</span>
          </h2>
          <Paragraph>{t.uniCredit.intro}</Paragraph>
          <SubHeading>{t.uniCredit.pegTitle}</SubHeading>
          <Paragraph>{t.uniCredit.pegBody}</Paragraph>
          <SubHeading>{t.uniCredit.feesTitle}</SubHeading>
          <List items={t.uniCredit.feesItems} />
          <SubHeading>{t.uniCredit.treasuryTitle}</SubHeading>
          <Paragraph>{t.uniCredit.treasuryBody}</Paragraph>
          <SubHeading>{t.uniCredit.flowTitle}</SubHeading>
          <List items={t.uniCredit.flowItems} />
          <SubHeading>{t.uniCredit.apiTitle}</SubHeading>
          <List items={t.uniCredit.apiItems} />
          <InfoBox title={t.uniCredit.settingsTitle} variant="info">
            {t.uniCredit.settingsBody}
          </InfoBox>
          <Paragraph>{t.uniCredit.docsMarkdown}</Paragraph>
        </div>
      ),
    },
    {
      id: 'security',
      title: st.security,
      icon: Shield,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-gradient-primary">{t.security.titleGradient}</span>
          </h2>
          <Paragraph>{t.security.intro}</Paragraph>
          <SubHeading>{t.security.authTitle}</SubHeading>
          <List items={t.security.authItems} />
          <SubHeading>{t.security.sandboxTitle}</SubHeading>
          <List items={t.security.sandboxItems} />
          <SubHeading>{t.security.dataProtectionTitle}</SubHeading>
          <List items={t.security.dataProtectionItems} />
          <SubHeading>{t.security.monitoringTitle}</SubHeading>
          <List items={t.security.monitoringItems} />
          <InfoBox title={t.security.firstPasswordTitle} variant="warning">
            {t.security.firstPasswordBodyPrefix}
            <code>{t.security.firstPasswordPath}</code>
            {t.security.firstPasswordBodySuffix}
          </InfoBox>
        </div>
      ),
    },
    {
      id: 'director',
      title: st.director,
      icon: BarChart3,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Director <span className="text-gradient-primary">{t.director.titleGradient}</span>
          </h2>
          <Paragraph>{t.director.intro}</Paragraph>
          <SubHeading>{t.director.analysisCycleTitle}</SubHeading>
          <List items={t.director.cycleItems} />
          <SubHeading>{t.director.metricsTitle}</SubHeading>
          <div className="grid md:grid-cols-2 gap-4 my-4">
            {t.director.metricCards.map((card) => (
              <GlassCard key={card.title} className="p-4">
                <h4 className="text-white font-semibold mb-2">{card.title}</h4>
                <ul className="text-sm text-gray-400 space-y-1">
                  {card.items.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </GlassCard>
            ))}
          </div>
          <SubHeading>{t.director.autoActionsTitle}</SubHeading>
          <Paragraph>{t.director.autoActionsIntro}</Paragraph>
          <List items={t.director.autoActionsItems} />
          <SubHeading>{t.director.reportFormatTitle}</SubHeading>
          <Paragraph>{t.director.reportFormatIntro}</Paragraph>
          <List items={t.director.reportFormatItems} />
        </div>
      ),
    },
    {
      id: 'configuration',
      title: st.configuration,
      icon: FileText,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-gradient-primary">{t.configuration.titleGradient}</span>
          </h2>
          <Paragraph>{t.configuration.intro}</Paragraph>
          <SubHeading>{t.configuration.modelProvidersTitle}</SubHeading>
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
          <SubHeading>{t.configuration.routingRulesTitle}</SubHeading>
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
          <SubHeading>{t.configuration.globalConfigTitle}</SubHeading>
          <SubHeading>{t.configuration.qualityBlockTitle}</SubHeading>
          <List items={t.configuration.qualityBlockItems} />
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
          <SubHeading>{t.configuration.themesTitle}</SubHeading>
          <Paragraph>{t.configuration.themesIntro}</Paragraph>
          <List items={t.configuration.themeItems} />
        </div>
      ),
    },

  ];
}
