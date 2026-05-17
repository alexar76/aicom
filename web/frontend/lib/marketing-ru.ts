import type { MarketingStrings } from './marketing';

export const MARKETING_RU: MarketingStrings = {
  brandName: 'AI-Factory',
  navGenerateLanding: 'Сгенерировать лендинг',
  navExplore: 'Обзор',
  navProducts: 'Продукты',
  navDocs: 'Документация',
  navAdmin: 'Админка',
  navMore: 'Ещё',
  navHome: 'Главная',
  navFeatures: 'Возможности',
  navAbout: 'О проекте',
  navUpdates: 'Обновления',
  navBlog: 'Блог',
  navLaunchKit: 'Launch Kit',
  navBadge: 'Бейдж',
  navIdea: 'Идея',
  navBenchmark: 'Бенчмарк',
  heroBadge: 'Одна фабрика — чёткие лендинги по фразе, полноценные приложения из админки',
  heroVisualEyebrow: 'За 12 секунд — как это выглядит',
  heroVisualTitle: 'Идея → агенты → превью в песочнице — живой пайплайн, не макет',
  heroVisualCaption:
    'Запись с работающей фабрики: вход в админку, стадии пайплайна, готовый лендинг в sandbox. Ваш бриф проходит тот же путь.',
  heroWatchDemo: 'Смотреть проход',
  heroTitleLead: 'Готовые страницы',
  heroTitleRest: 'и реальные продукты — из одного брифа',
  heroSubtitle:
    'Строка выше — быстрая маркетинговая страница с превью после QA: промо, листы ожидания, «покажите что-то настоящее». Когда нужны API, данные, авторизация и многоэкранные продукты — тот же конвейер агентов из админки или Director. Песочница и опциональная оплата on-chain — для обоих путей.',
  heroHint:
    'Ниже — живые примеры от брошюрных лендингов до full-stack. Поле фразы намеренно лёгкое; админка — очередь сложной работы. Один движок, не «игрушечный» стек.',
  heroGeneratorEyebrow: 'Начните здесь — гостевой тест (сначала лендинг)',
  heroGeneratorTitle: 'Опишите задачу. Отдадим страницу с превью.',
  heroPhraseTitle: 'Ваша фраза → аккуратный маркетинговый лендинг',
  heroPhrasePlaceholder:
    'напр. Неоновый SaaS waitlist для AI-планировщика — hero, 3 преимущества, тарифы, футер со ссылками…',
  heroSloganLineLabel: 'Слоган или однострочный бриф бизнеса',
  heroSloganLinePlaceholder:
    'напр. Люксовые кожаные кошельки D2C — hero, история мастерства, 3 причины купить, email, футер',
  heroPricingLine:
    'Один клик — страница в очереди · песочница после QA · опциональная оплата — или админка для полноценного приложения.',
  heroGuestBuildCta: 'Собрать бизнес-лендинг',
  heroGuestHelp:
    'Гости: без входа. Путь оптимизирован под одну убедительную страницу. Для multi-tenant, бэкендов и интеграций — админка: те же агенты и гейты, богаче профиль доставки.',
  heroPhraseTooShort: 'Минимум 8 символов, чтобы бриф был конкретным.',
  heroCtaPhrase: 'Открыть админку с этим текстом',
  heroCtaAdminOnly: 'Продвинутое — только админка',
  ctaPrimary: 'Открыть админку и собрать',
  ctaSecondary: 'Смотреть примеры',
  stats: {
    agents: 'AI-агенты',
    agentsValue: '12',
    pipeline: 'Стадии пайплайна',
    pipelineValue: '14',
    llm: 'LLM-провайдеры',
    llmValue: '4+',
    chains: 'Сети',
    chainsValue: '3',
  },
  featuresIntroGradientWord: 'Сделано',
  featuresIntroRest: 'для скорости и глубины',
  featuresIntroSubtitle:
    'Лендинги — гостевой результат по умолчанию; автономные и админские идеи часто становятся продуктами — один пайплайн, разный delivery_profile, те же гейты.',
  features: [
    {
      iconKey: 'sparkles',
      title: 'Одна фраза → презентабельная страница',
      description:
        'Предложение становится брифом через те же стадии, что и автономные сборки — HTML/CSS/JS с превью в песочнице; гейты отсекают пустышки.',
      gradient: 'from-indigo-500 to-purple-500',
    },
    {
      iconKey: 'bot',
      title: 'Специализированные агенты',
      description:
        '12 ролей (Analyst, PM, Methodologist, Architect, Designer/UX, Developer, QA, Security, DevOps, Marketing, Sales, Evolution) — каждый шаг ограничен для поддерживаемости.',
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      iconKey: 'shield',
      title: 'Гейты качества и безопасности',
      description:
        'Демо-проверки, headless smoke, опциональные правила витрины — циклы доработки до готовности к показу.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      iconKey: 'rocket',
      title: 'Та же взлётная полоса, что у автономного режима',
      description:
        'Исследование → спека → архитектура → код → QA → security → DevOps → маркетинг → продажи → эволюция. Автономный режим кормится рынком; по запросу — вашей фразой.',
      gradient: 'from-orange-500 to-red-500',
    },
    {
      iconKey: 'chart',
      title: 'Director AI',
      description:
        'Мета-агент по расписанию смотрит здоровье пайплайна и направляет автономные улучшения.',
      gradient: 'from-cyan-500 to-blue-500',
    },
    {
      iconKey: 'coins',
      title: 'Витрина с крипто-оплатой',
      description:
        'Доступная цена разового лендинга (~$5 USDT, если агенты не задали прайс), мультичейн checkout — покупатель платит on-chain, вы отдаёте файлы.',
      gradient: 'from-yellow-500 to-amber-500',
    },
  ],
  productsTitle: 'Примеры на витрине',
  productsSubtitle:
    'Отдельно: брошюрные лендинги (генератор в hero) и полные продукты (админка / автономный пайплайн). Все прошли гейты качества.',
  productsLandingsTitle: 'Маркетинговые лендинги',
  productsLandingsSubtitle:
    'Одностраничные брошюры — тот же путь доставки, что у поля фразы вверху страницы.',
  productsFullTitle: 'Полные продукты',
  productsFullSubtitle:
    'Приложения и сервисы с бэкендом, БД и compose-репозиториями — из админки или Director.',
  ctaBannerTitle: 'Готовы выпустить следующую страницу или продукт?',
  ctaBannerSubtitle:
    'Разверните фабрику, подключите LLM-ключи, используйте поле фразы для лендинга или админку для полной сборки — те же агенты и планка качества.',
  ctaBannerPrimary: 'Открыть админку',
  ctaBannerSecondary: 'Документация',
  footerTagline: 'AI-Factory v2.1',
  footerDocumentation: 'Документация',
  footerBlog: 'Блог',
  footerLaunchKit: 'Launch Kit',
  footerBadge: 'Встраиваемый бейдж',
  footerApiReference: 'Справка API',
  footerGithub: 'GitHub',
  footerAdminPanel: 'Админ-панель',
  pipelineSectionTitle: 'Один пайплайн — два входа',
  pipelineSectionSubtitle:
    'Автономный режим: исследование рынка и идеи; по запросу — ваша фраза как бриф. Тот же путь агентов — спека, сборка, QA и дальше.',
  pipelineDesignerEyebrow: 'Продуктовый опыт',
  pipelineDesignerTitle: 'Слой дизайнера — современный UI по умолчанию',
  pipelineDesignerBody:
    'До кода Architect формирует `ui_experience`: токены, типографика, motion и визуальный акцент. Developer обязан следовать этому для браузерных артефактов — лендинги выглядят как продукт, а не серые AI-блоки.',
};
