import type { MarketingStrings } from './marketing';

export const MARKETING_ZH: MarketingStrings = {
  brandName: 'AI-Factory',
  navGenerateLanding: '生成着陆页',
  navExplore: '探索',
  navProducts: '产品',
  navDocs: '文档',
  navAdmin: 'Admin',
  navMore: '更多',
  navHome: '首页',
  navFeatures: '功能',
  navAbout: '关于',
  navUpdates: '更新',
  navBlog: '博客',
  navLaunchKit: 'Launch Kit',
  navBadge: '徽章',
  navIdea: '创意',
  navBenchmark: '基准测试',
  navFactoryIq: 'Factory IQ',
  heroBadge: '一座工厂——一句话生成精致着陆页，从 Admin 构建完整应用',
  heroVisualEyebrow: '看工厂如何运转',
  heroVisualTitle: '创意 → 智能体 → 可交付产品——完整演示在 YouTube',
  heroVisualCaption: '产品演示与流水线导览：',
  heroWatchDemo: '在 YouTube 打开',
  heroTitleLead: '即刻上线的页面',
  heroTitleRest: '与真实应用——出自同一份需求',
  heroSubtitle:
    '上方的输入框可快速生成一份可分享的营销页面，经 QA 后即可预览——非常适合促销、等候名单以及「拿点真东西给我看」的时刻。当需求扩展到 API、数据、鉴权和多屏产品时，同一条智能体流水线会从 Admin 或 Director 运行更深入的构建。沙箱预览与可选的链上结账适用于两条路径。',
  heroHint:
    '下方是从宣传型着陆页到全栈产品的实时示例。短语输入框刻意做得轻量；Admin 才是复杂工作排队的地方——同一套引擎，绝非「简化版」玩具。',
  heroGeneratorEyebrow: '从这里开始——访客试用（着陆页优先）',
  heroGeneratorTitle: '写下你的需求，我们交付一份可预览的页面。',
  heroPhraseTitle: '你的一句话 → 一份精致的营销页面',
  heroPhrasePlaceholder:
    '例如：为一款 AI 排程工具做霓虹风 SaaS 等候名单页——hero、3 项优势、价格卡片、带链接的页脚……',
  heroSloganLineLabel: '标语或一句话业务简介',
  heroSloganLinePlaceholder:
    '例如：奢华真皮钱包 D2C——hero、工艺故事、3 个购买理由、邮箱收集、页脚',
  heroStylePresetLabel: '视觉风格预设',
  heroStylePresetAuto: '自动——根据你的简介挑选',
  heroStylePresetHint: '20 种精选方向（glassmorphism、editorial、cyberpunk HUD……）。快速路径：mini-spec → architect → developer → QA。',
  heroPricingLine:
    '一键即可将页面排入队列并追踪 · QA 后进入沙箱 · 可选结账——或在需要完整应用时切换到 Admin。',
  heroGuestBuildCta: '构建业务着陆页',
  heroGuestHelp:
    '访客：无需登录。此路径针对单页可信度进行优化。若需多租户应用、后端、集成及长期维护的产品，请打开 Admin——同样的智能体与门控，更丰富的交付档案。',
  heroPhraseTooShort: '请至少输入 8 个字符，让简介更具体。',
  heroCtaPhrase: '用这段文字打开 Admin',
  heroCtaAdminOnly: '进阶——仅限 Admin',
  statusBannerPreLaunch: 'v0.1——预发布',
  statusBannerInPipeline: '{n} 个在流水线中',
  statusBannerShipped: '{n} 个已交付',
  ctaPrimary: '打开 Admin 并构建',
  ctaSecondary: '浏览示例',
  stats: {
    agents: 'AI 智能体',
    agentsValue: '12',
    pipeline: '流水线阶段',
    pipelineValue: '14',
    llm: 'LLM 提供方',
    llmValue: '4+',
    chains: '链',
    chainsValue: '3',
  },
  featuresIntroGradientWord: '为速度',
  featuresIntroRest: '与深度而生',
  featuresIntroSubtitle:
    '着陆页是默认的访客交付物；自主与 Admin 排队的创意常常成长为完整产品——同一条流水线，不同的 delivery_profile，相同的门控。',
  features: [
    {
      iconKey: 'sparkles',
      title: '一句话 → 可展示的页面',
      description:
        '你的句子会经由与自主构建相同的各个阶段变成干系人简介——你可在沙箱中预览的 HTML/CSS/JS；门控会拒绝空洞的半成品。',
      gradient: 'from-indigo-500 to-purple-500',
    },
    {
      iconKey: 'bot',
      title: '专业化智能体',
      description:
        '每个阶段配备专业角色（Analyst、PM、Methodologist、Architect、Designer/UX、Developer、QA、Security、DevOps、Marketing、Sales、Evolution）——每一步都有边界，确保产出可维护。完整清单见 `agents/`。',
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      iconKey: 'shield',
      title: '质量与安全门控',
      description:
        '演示检查、无头浏览器冒烟测试、可选的交易市场规则——反复返工，直到产品达到可展示状态。',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      iconKey: 'rocket',
      title: '与自主模式同一条跑道',
      description:
        '调研 → 规格 → 架构 → 编码 → QA → 安全 → DevOps → 营销 → 销售 → 演进。自主模式从市场中萌发创意；按需模式从你的一句话萌发——没有二等流水线。',
      gradient: 'from-orange-500 to-red-500',
    },
    {
      iconKey: 'chart',
      title: 'Director AI',
      description:
        '元智能体按计划审查流水线健康状况，并引导自主改进。',
      gradient: 'from-cyan-500 to-blue-500',
    },
    {
      iconKey: 'coins',
      title: '支持加密支付的店面',
      description:
        '一次性着陆页价格亲民（当智能体未标定价时约 $5 USDT），多链结账——买家链上付款，你交付文件。',
      gradient: 'from-yellow-500 to-amber-500',
    },
  ],
  productsTitle: '交易市场示例',
  productsSubtitle:
    '分开浏览：宣传型着陆页（hero 生成器）与完整产品（Admin / 自主流水线）。所有条目均已通过质量门控。',
  productsLandingsTitle: '营销着陆页',
  productsLandingsSubtitle:
    '单页宣传型构建——与本页顶部短语输入框相同的交付路径。',
  productsFullTitle: '完整产品',
  productsFullSubtitle:
    '拥有真实后端、数据存储及便于 compose 的仓库的应用与服务——从 Admin 或 Director 排队。',
  ctaBannerTitle: '准备好交付下一个页面或产品了吗？',
  ctaBannerSubtitle:
    '自托管这座工厂，接入 LLM 密钥，然后用短语输入框做着陆页、用 Admin 做完整构建——同样的智能体，同样的质量标准。',
  ctaBannerPrimary: '打开 Admin',
  ctaBannerSecondary: '文档',
  footerTagline: 'AI-Factory v2.1',
  footerDocumentation: '文档',
  footerBlog: '博客',
  footerLaunchKit: 'Launch Kit',
  footerBadge: '可嵌入徽章',
  footerApiReference: 'API 参考',
  footerGithub: 'GitHub',
  footerAdminPanel: 'Admin 面板',
  footerTerms: '条款',
  footerPrivacy: '隐私',
  pipelineSectionTitle: '一条流水线，两扇前门',
  pipelineSectionSubtitle:
    '自主模式吸收市场调研和生成的创意；按需模式以你的一句话作为简介。同一条智能体路径——规格、构建、QA 以及之后的一切。',
  pipelineDesignerEyebrow: '产品体验',
  pipelineDesignerTitle: '设计师层——默认现代 UI',
  pipelineDesignerBody:
    '在交付代码之前，Architect 会输出一份结构化的 `ui_experience` 简介：令牌、排版、动效以及标志性的视觉高光。Developer 将其视为浏览器交付物的约束——于是着陆页读起来像是有意为之的产品设计，而非千篇一律的 AI 灰盒。',
  architectureEyebrow: '运行时拓扑',
  architectureTitle: '架构一览',
  architectureSubtitle:
    '统一的控制平面：Web 层、后台工作进程、路由模型以及持久化工作区——以围绕智能体舰队的实时轨道呈现。',
  architectureHubLabel: '智能体',
  architectureHubRoles: 'PM · Architect · Dev · QA · Sec · Ops · Mkt · Sales · Evolution',
  architectureHubFooter: '单一流水线 · 共享门控',
  architectureNodes: [
    { label: 'Next.js', sub: '店面' },
    { label: 'FastAPI', sub: '公共与 admin API' },
    { label: 'Pipeline worker', sub: '质量门控' },
    { label: 'Director AI', sub: '信号与报告' },
    { label: 'LLM router', sub: '多提供方' },
    { label: 'Data plane', sub: 'SQLite · 制品' },
  ],
};
