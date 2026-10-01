import type { MarketingStrings } from './marketing';

export const MARKETING_FR: MarketingStrings = {
  brandName: 'AI-Factory',
  navGenerateLanding: 'Générer une landing',
  navExplore: 'Explorer',
  navProducts: 'Produits',
  navDocs: 'Docs',
  navAdmin: 'Admin',
  navMore: 'Plus',
  navHome: 'Accueil',
  navFeatures: 'Fonctionnalités',
  navAbout: 'À propos',
  navUpdates: 'Nouveautés',
  navBlog: 'Blog',
  navLaunchKit: 'Launch Kit',
  navBadge: 'Badge',
  navIdea: 'Idée',
  navBenchmark: 'Benchmark',
  navFactoryIq: 'Factory IQ',
  heroBadge: 'Une seule usine — des landings nettes en une phrase, des applications complètes depuis l’Admin',
  heroVisualEyebrow: 'Voyez l’usine à l’œuvre',
  heroVisualTitle: 'Idée → agents → produit livrable — visite complète sur YouTube',
  heroVisualCaption: 'Démo produit et tour du pipeline :',
  heroWatchDemo: 'Ouvrir sur YouTube',
  heroTitleLead: 'Des pages prêtes à lancer',
  heroTitleRest: 'et de vraies applis — à partir du même brief',
  heroSubtitle:
    'La ligne ci-dessus donne une page marketing rapide et partageable, prévisualisable après le QA — idéale pour les promos, les listes d’attente et les moments « montrez-moi du concret ». Quand le périmètre grandit vers des API, des données, de l’authentification et des produits multi-écrans, le même pipeline d’agents lance des builds plus profonds depuis l’Admin ou le Director. La prévisualisation en bac à sable et le paiement on-chain optionnel s’appliquent aux deux voies.',
  heroHint:
    'Ci-dessous : des exemples réels, des landings brochure aux listings full-stack. Le champ de phrase est volontairement léger ; c’est l’Admin qui met en file le travail complexe — un seul moteur, pas un stack « lite » de jouet.',
  heroGeneratorEyebrow: 'Commencez ici — essai invité (landing d’abord)',
  heroGeneratorTitle: 'Décrivez votre besoin. On livre une page prévisualisable.',
  heroPhraseTitle: 'Votre phrase → une page marketing soignée',
  heroPhrasePlaceholder:
    'p. ex. Liste d’attente SaaS néon pour un outil de planification IA — hero, 3 bénéfices, cartes de tarifs, footer avec liens…',
  heroSloganLineLabel: 'Slogan ou brief business en une ligne',
  heroSloganLinePlaceholder:
    'p. ex. Portefeuilles en cuir de luxe D2C — hero, histoire du savoir-faire, 3 raisons d’acheter, capture d’email, footer',
  heroStylePresetLabel: 'Préréglage de style visuel',
  heroStylePresetAuto: 'Auto — d’après votre brief',
  heroStylePresetHint: '20 directions sélectionnées (glassmorphism, editorial, cyberpunk HUD, …). Voie rapide : mini-spec → architect → developer → QA.',
  heroPricingLine:
    'Un clic met une page en file, suivable · bac à sable après le QA · paiement optionnel — ou passez à l’Admin quand il vous faut une application complète.',
  heroGuestBuildCta: 'Créer une landing business',
  heroGuestHelp:
    'Invités : sans connexion. Cette voie est optimisée pour une seule page crédible. Pour les applis multi-tenant, les backends, les intégrations et les produits durables, ouvrez l’Admin — mêmes agents et mêmes gates, profil de livraison plus riche.',
  heroPhraseTooShort: 'Utilisez au moins 8 caractères pour que le brief soit concret.',
  heroCtaPhrase: 'Ouvrir l’admin avec ce texte',
  heroCtaAdminOnly: 'Avancé — admin uniquement',
  statusBannerPreLaunch: 'v0.1 — avant lancement',
  statusBannerInPipeline: '{n} dans le pipeline',
  statusBannerShipped: '{n} livré(s)',
  ctaPrimary: 'Ouvrir l’admin et créer',
  ctaSecondary: 'Parcourir les exemples',
  stats: {
    agents: 'Agents IA',
    agentsValue: '12',
    pipeline: 'Étapes du pipeline',
    pipelineValue: '14',
    llm: 'Fournisseurs LLM',
    llmValue: '4+',
    chains: 'Chaînes',
    chainsValue: '3',
  },
  featuresIntroGradientWord: 'Conçu',
  featuresIntroRest: 'pour la vitesse et la substance',
  featuresIntroSubtitle:
    'Les landings sont le livrable invité par défaut ; les idées autonomes et mises en file depuis l’Admin deviennent souvent des produits complets — un seul pipeline, un delivery_profile différent, des gates identiques.',
  features: [
    {
      iconKey: 'sparkles',
      title: 'Une phrase → une page présentable',
      description:
        'Votre phrase devient le brief des parties prenantes en traversant les mêmes étapes que les builds autonomes — du HTML/CSS/JS que vous prévisualisez dans le bac à sable ; les gates rejettent les ébauches creuses.',
      gradient: 'from-indigo-500 to-purple-500',
    },
    {
      iconKey: 'bot',
      title: 'Agents spécialisés',
      description:
        'Des rôles spécialisés par étape (Analyst, PM, Methodologist, Architect, Designer/UX, Developer, QA, Security, DevOps, Marketing, Sales, Evolution) — chaque étape est bornée pour que les livrables restent maintenables. Voir `agents/` pour la liste complète.',
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      iconKey: 'shield',
      title: 'Gates de qualité et de sécurité',
      description:
        'Vérifications de démo, smoke test en navigateur headless, règles de place de marché optionnelles — les boucles de reprise tournent jusqu’à ce que le produit soit prêt à montrer.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      iconKey: 'rocket',
      title: 'La même piste de lancement que l’autonome',
      description:
        'Recherche → spec → architecture → code → QA → sécurité → DevOps → marketing → vente → évolution. L’autonome sème les idées depuis le marché ; à la demande, la graine vient de votre phrase — pas de pipeline de seconde zone.',
      gradient: 'from-orange-500 to-red-500',
    },
    {
      iconKey: 'chart',
      title: 'Director AI',
      description:
        'Un méta-agent examine la santé du pipeline selon un calendrier et pilote les améliorations autonomes.',
      gradient: 'from-cyan-500 to-blue-500',
    },
    {
      iconKey: 'coins',
      title: 'Vitrine prête pour la crypto',
      description:
        'Prix abordable pour une landing en une passe (environ 5 $ USDT quand les agents n’indiquent pas de tarif), paiement multi-chaînes — les acheteurs paient on-chain, vous livrez les fichiers.',
      gradient: 'from-yellow-500 to-amber-500',
    },
  ],
  productsTitle: 'Exemples de la place de marché',
  productsSubtitle:
    'Parcourez-les séparément : landings brochure (générateur du hero) vs. produits complets (pipeline admin / autonome). Tous les listings ont passé les gates de qualité.',
  productsLandingsTitle: 'Pages marketing (landings)',
  productsLandingsSubtitle:
    'Builds brochure d’une seule page — même voie de livraison que le champ de phrase en haut de cette page.',
  productsFullTitle: 'Produits complets',
  productsFullSubtitle:
    'Applis et services avec de vrais backends, des bases de données et des dépôts compatibles compose — mis en file depuis l’Admin ou le Director.',
  ctaBannerTitle: 'Prêt à livrer votre prochaine page ou produit ?',
  ctaBannerSubtitle:
    'Auto-hébergez l’usine, connectez vos clés LLM, puis utilisez le champ de phrase pour une landing ou l’Admin pour un build complet — mêmes agents, même exigence de qualité.',
  ctaBannerPrimary: 'Ouvrir l’admin',
  ctaBannerSecondary: 'Documentation',
  footerTagline: 'AI-Factory v2.1',
  footerDocumentation: 'Documentation',
  footerBlog: 'Blog',
  footerLaunchKit: 'Launch Kit',
  footerBadge: 'Badge intégrable',
  footerApiReference: 'Référence API',
  footerGithub: 'GitHub',
  footerAdminPanel: 'Panneau Admin',
  footerTerms: 'Conditions',
  footerPrivacy: 'Confidentialité',
  pipelineSectionTitle: 'Un seul pipeline, deux portes d’entrée',
  pipelineSectionSubtitle:
    'Le mode autonome alimente la recherche de marché et les idées générées ; à la demande, votre phrase sert de brief. Même parcours d’agents — spec, build, QA et au-delà.',
  pipelineDesignerEyebrow: 'Expérience produit',
  pipelineDesignerTitle: 'Couche Designer — une UI moderne par défaut',
  pipelineDesignerBody:
    'Avant que le code parte, l’Architect émet un brief `ui_experience` structuré : tokens, typographie, motion et un moment visuel signature. Le Developer le traite comme contraignant pour les livrables navigateur — ainsi les landings se lisent comme un design produit intentionnel, pas comme des boîtes grises IA génériques.',
  architectureEyebrow: 'Topologie du runtime',
  architectureTitle: 'L’architecture en un coup d’œil',
  architectureSubtitle:
    'Un seul plan de contrôle : couche web, workers d’arrière-plan, modèles routés et workspace durable — présenté comme une orbite vivante autour de la flotte d’agents.',
  architectureHubLabel: 'Agents',
  architectureHubRoles: 'PM · Architect · Dev · QA · Sec · Ops · Mkt · Sales · Evolution',
  architectureHubFooter: 'Un seul pipeline · gates partagés',
  architectureNodes: [
    { label: 'Next.js', sub: 'Vitrine' },
    { label: 'FastAPI', sub: 'API publique et admin' },
    { label: 'Pipeline worker', sub: 'Gates de qualité' },
    { label: 'Director AI', sub: 'Signaux et rapports' },
    { label: 'LLM router', sub: 'Multi-fournisseurs' },
    { label: 'Data plane', sub: 'SQLite · artefacts' },
  ],
  logosEyebrow: 'Intelligence fédérée · produit en ligne',
  logosTitle: 'LOGOS transforme tout l’écosystème en un observatoire unique.',
  logosBody:
    'Il interroge Hub, MOMUS, SKOPOS et Treasury, stocke des instantanés réels, détecte les anomalies par z-score glissant, corrèle sécurité, latence, réputation et économie, puis répond via un assistant protégé.',
  logosReadOnly: 'Lecture seule par construction — jamais de scan, remédiation, paiement ou déploiement',
  logosDashboard: 'Ouvrir LOGOS en direct',
  logosSource: 'Code source',
  logosDocs: 'Fonctionnement des analyses',
};
