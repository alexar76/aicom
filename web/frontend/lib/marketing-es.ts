import type { MarketingStrings } from './marketing';

export const MARKETING_ES: MarketingStrings = {
  brandName: 'AI-Factory',
  navGenerateLanding: 'Generar landing',
  navExplore: 'Explorar',
  navProducts: 'Productos',
  navDocs: 'Docs',
  navAdmin: 'Admin',
  navMore: 'Más',
  navHome: 'Inicio',
  navFeatures: 'Funciones',
  navAbout: 'Acerca de',
  navUpdates: 'Novedades',
  navBlog: 'Blog',
  navLaunchKit: 'Launch Kit',
  navBadge: 'Badge',
  navIdea: 'Idea',
  navBenchmark: 'Benchmark',
  heroBadge: 'Una fábrica — landings claros en una frase, apps completas desde Admin',
  heroVisualEyebrow: 'Véalo en 12 segundos',
  heroVisualTitle: 'Idea → agentes → preview en sandbox — pipeline real, no mockup',
  heroVisualCaption:
    'Grabado en una fábrica en vivo: login admin, etapas del pipeline, landing generado en sandbox. Su brief sigue el mismo camino.',
  heroWatchDemo: 'Reproducir recorrido',
  heroTitleLead: 'Páginas listas para lanzar',
  heroTitleRest: 'y apps reales — del mismo brief',
  heroSubtitle:
    'La línea de arriba: una página de marketing rápida con vista previa tras QA — ideal para promos y listas de espera. Cuando el alcance crece (APIs, datos, auth, productos multipantalla), el mismo pipeline corre builds profundos desde Admin o Director. Sandbox y checkout on-chain opcional en ambos caminos.',
  heroHint:
    'Abajo: ejemplos en vivo de landings brochure a productos full-stack. La caja de frase es ligera a propósito; Admin es la cola de trabajo compleja — un motor, no un stack “lite”.',
  heroGeneratorEyebrow: 'Empiece aquí — prueba invitado (landing primero)',
  heroGeneratorTitle: 'Escriba lo que necesita. Entregamos una página con preview.',
  heroPhraseTitle: 'Su frase → landing de marketing pulido',
  heroPhrasePlaceholder:
    'ej. Waitlist SaaS neón para planificador AI — hero, 3 beneficios, precios, footer con enlaces…',
  heroSloganLineLabel: 'Eslogan o brief de negocio en una línea',
  heroSloganLinePlaceholder:
    'ej. Carteras de cuero D2C — hero, historia artesanal, 3 razones, email, footer',
  heroPricingLine:
    'Un clic encola la página · sandbox tras QA · checkout opcional — o Admin para app completa.',
  heroGuestBuildCta: 'Crear landing de negocio',
  heroGuestHelp:
    'Invitados: sin login. Este camino optimiza una página creíble. Para multi-tenant, backends e integraciones, abra Admin — mismos agentes y gates, perfil de entrega más rico.',
  heroPhraseTooShort: 'Use al menos 8 caracteres para un brief concreto.',
  heroCtaPhrase: 'Abrir admin con este texto',
  heroCtaAdminOnly: 'Avanzado — solo admin',
  ctaPrimary: 'Abrir admin y construir',
  ctaSecondary: 'Ver ejemplos',
  stats: {
    agents: 'Agentes IA',
    agentsValue: '12',
    pipeline: 'Etapas del pipeline',
    pipelineValue: '14',
    llm: 'Proveedores LLM',
    llmValue: '4+',
    chains: 'Cadenas',
    chainsValue: '3',
  },
  featuresIntroGradientWord: 'Hecho',
  featuresIntroRest: 'para velocidad y sustancia',
  featuresIntroSubtitle:
    'Landings son el entregable invitado por defecto; ideas autónomas y en cola suelen ser productos completos — un pipeline, distinto delivery_profile, mismos gates.',
  features: [
    {
      iconKey: 'sparkles',
      title: 'Una frase → página presentable',
      description:
        'Su frase es el brief por las mismas etapas que builds autónomos — HTML/CSS/JS con preview en sandbox; los gates rechazan stubs vacíos.',
      gradient: 'from-indigo-500 to-purple-500',
    },
    {
      iconKey: 'bot',
      title: 'Agentes especializados',
      description:
        'Doce roles (Analyst, PM, Methodologist, Architect, Designer/UX, Developer, QA, Security, DevOps, Marketing, Sales, Evolution) — cada paso acotado.',
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      iconKey: 'shield',
      title: 'Gates de calidad y seguridad',
      description:
        'Checks demo, smoke headless, reglas de marketplace opcionales — bucles de rework hasta estar listo para mostrar.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      iconKey: 'rocket',
      title: 'Misma pista que el modo autónomo',
      description:
        'Research → spec → arquitectura → código → QA → security → DevOps → marketing → ventas → evolución. Semillas autónomas del mercado; bajo demanda, su frase.',
      gradient: 'from-orange-500 to-red-500',
    },
    {
      iconKey: 'chart',
      title: 'Director AI',
      description:
        'Meta-agente revisa la salud del pipeline y guía mejoras autónomas.',
      gradient: 'from-cyan-500 to-blue-500',
    },
    {
      iconKey: 'coins',
      title: 'Vitrina lista para cripto',
      description:
        'Precio accesible de landing (~$5 USDT si los agentes no fijan lista), checkout multichain — el comprador paga on-chain, usted entrega archivos.',
      gradient: 'from-yellow-500 to-amber-500',
    },
  ],
  productsTitle: 'Ejemplos en marketplace',
  productsSubtitle:
    'Navegue por separado: landings brochure (generador hero) vs productos completos (admin / pipeline autónomo). Todos pasaron gates de calidad.',
  productsLandingsTitle: 'Landings de marketing',
  productsLandingsSubtitle:
    'Páginas brochure de una sola pantalla — mismo camino que la caja de frase arriba.',
  productsFullTitle: 'Productos completos',
  productsFullSubtitle:
    'Apps y servicios con backends reales, datos y repos compose-friendly — desde Admin o Director.',
  ctaBannerTitle: '¿Listo para lanzar su próxima página o producto?',
  ctaBannerSubtitle:
    'Auto-hospede la fábrica, conecte claves LLM, use la caja de frase para landing o Admin para build completo — mismos agentes, misma barra de calidad.',
  ctaBannerPrimary: 'Abrir admin',
  ctaBannerSecondary: 'Documentación',
  footerTagline: 'AI-Factory v2.1',
  footerDocumentation: 'Documentación',
  footerBlog: 'Blog',
  footerLaunchKit: 'Launch Kit',
  footerBadge: 'Insignia embebible',
  footerApiReference: 'Referencia API',
  footerGithub: 'GitHub',
  footerAdminPanel: 'Panel de administración',
  pipelineSectionTitle: 'Un pipeline, dos puertas',
  pipelineSectionSubtitle:
    'Modo autónomo: research de mercado e ideas; bajo demanda usa su frase como brief. Mismo camino de agentes — spec, build, QA y más.',
  pipelineDesignerEyebrow: 'Experiencia de producto',
  pipelineDesignerTitle: 'Capa diseñador — UI moderna por defecto',
  pipelineDesignerBody:
    'Antes del código, Architect emite un brief `ui_experience`: tokens, tipografía, motion y un momento visual distintivo. Developer lo trata como vinculante — landings con diseño intencional, no cajas grises genéricas de IA.',
};
