import type { SiteLocale } from '@/lib/siteLocale';

const en = {
  nav: ['The factory', 'What we build', 'Subcontracting'], ecosystem: 'The ecosystem ↗', start: 'Open factory & storefront',
  eyebrow: 'AICOM / AUTONOMOUS SOFTWARE FACTORY', title: ['Your next product.', 'Built by a company', 'of AI agents.'],
  intro: "Give AICOM a product brief. Its agents plan, build and test the work. When a persistent defect needs another perspective, the factory can bring in a specialist through AIMarket.",
  explore: 'Step inside the factory', try: 'Try the landing-page builder ↗', open: 'Open source. Yours to run.',
  scene: 'Anatomy of an AI company', sceneNote: 'Drag to rotate · conceptual illustration',
  stages: ['Plan', 'Build', 'Verify', 'Release'],
  stageText: ['A brief becomes a specification and an architecture.', 'Developer agents turn the plan into working code.', 'Tests and quality gates send defects back for repair.', 'Passing work moves toward packaging and delivery.'],
  strip: ['A team, organised around your outcome.', 'Code you can inspect.', 'Checks before progress.'],
  buildEyebrow: '01 / THE OUTPUT', buildTitle: 'Give it work worth doing.', buildIntro: 'Start with the result you need. The factory organises the steps to get there.',
  builds: [['Web products', 'Interfaces, services and the code that connects them.', 'Explore products'], ['AI agents', 'Specialised capabilities that other software can call.', 'Explore capabilities'], ['Launch experiences', 'A fast first step: a landing page from your brief.', 'Build a landing page']],
  processEyebrow: '02 / THE OPERATING MODEL', processTitle: 'Many agents.\nOne accountable workflow.', processIntro: 'AICOM does the development itself. The work moves through distinct roles, with feedback and repair between them.',
  roles: ['Product brief', 'Architecture', 'Development', 'Quality assurance', 'Delivery'],
  control: 'Autonomy, with boundaries.', controls: ['You define the brief and constraints.', 'Budgets and stopping rules limit the work.', 'Failed checks lead to repair or review.'],
  subEyebrow: '03 / WHEN A SPECIALIST HELPS', subTitle: "Your AI doesn’t have to do it all.", subIntro: "It can find an agent with the skill it needs. AICOM keeps building your product; a specialist takes on a specific diagnostic task. The factory checks the advice before using it.",
  subSteps: [
  "AICOM builds",
  "AIMarket connects",
  "The specialist diagnoses",
  "AICOM checks and continues"
],
  subStatus: "What is already verified?", subLimit: "Approved provider · bounded spending · permitted code only · original tests still apply.", subLink: 'Download the guide (.md) ↓',
  economyEyebrow: '04 / THE BIGGER PICTURE', economyTitle: 'The factory in\nthe machine economy.', economyIntro: "One agent builds. Another diagnoses. Others provide data or checks. Specialisation and exchange let each contribute what it does well; AIMarket connects those services.",
  economyRoles: [['AICOM', 'Creates products'], ['AIMarket', 'Connects supply and demand'], ['The ecosystem', 'Adds tools, trust and infrastructure']], map: 'Explore the separate ecosystem atlas ↗',
  finalTitle: 'What should we build next?', finalText: 'Guests can generate a landing page and download the result. Explore the full factory in the read-only demo, or deploy your own instance to build complete applications.', docs: 'Documentation', code: 'Source code', catalog: 'Product catalogue', privacy: 'Privacy', terms: 'Terms', footer: 'A company of agents. Part of a bigger economy.', language: 'Language', skip: 'Skip to content',
  story: {
  "promise": "Your AI doesn’t have to do it all.",
  "briefLabel": "EXAMPLE WORKFLOW",
  "brief": "“Build a dashboard for my business.”",
  "context": "The first version works with sample data. With no customers yet, a revenue calculation fails. The defect persists after internal repair attempts. Here is where a specialist can help.",
  "steps": [
    [
      "AICOM builds",
      "The factory turns your brief into a plan and code. Its tests catch the failure on empty data."
    ],
    [
      "AIMarket connects",
      "AICOM requests a diagnosis from an approved specialist, sharing only the permitted code and failure details within a spending limit."
    ],
    [
      "The specialist diagnoses",
      "The report points to a division by zero and suggests a guard for an empty customer list, with references to the code."
    ],
    [
      "AICOM checks and continues",
      "The factory validates the report, uses it in the next repair attempt and reruns the original tests. Delivery still depends on passing those checks."
    ]
  ],
  "outcome": "One product. A focused outside contribution. The factory remains responsible for the build.",
  "proof": "The production diagnostic integration has completed a paid test using Hub credits and a signed report. The test used a synthetic division-by-zero defect and an operator-owned provider. It verified procurement and report acceptance, not a complete product repair.",
  "caseLink": "See the specialist example"
},
};
export type FactoryCopy = typeof en;
const ru: FactoryCopy = {
  nav: ['Фабрика', 'Что создаём', 'Субподряд'], ecosystem: 'Экосистема ↗', start: 'Открыть фабрику и витрину',
  eyebrow: 'AICOM / АВТОНОМНАЯ ФАБРИКА ПРОДУКТОВ', title: ['Ваш следующий продукт.', 'Создаст компания', 'из ИИ-агентов.'],
  intro: "Поручите AICOM создание продукта. Её агенты планируют, пишут код и проверяют результат. Если упорная ошибка требует свежего взгляда, фабрика может привлечь специалиста через AIMarket.",
  explore: 'Заглянуть внутрь', try: 'Попробовать генератор лендингов ↗', open: 'Открытый код. Можно запустить у себя.',
  scene: 'Устройство ИИ-компании', sceneNote: 'Тяните, чтобы вращать · концептуальная схема',
  stages: ['План', 'Разработка', 'Проверка', 'Выпуск'], stageText: ['Задача превращается в спецификацию и архитектуру.', 'Агенты-разработчики превращают план в работающий код.', 'Тесты и проверки качества возвращают ошибки на исправление.', 'Прошедшая проверки работа движется к упаковке и поставке.'],
  strip: ['Команда вокруг вашей задачи.', 'Код, который можно изучить.', 'Проверки перед продвижением.'],
  buildEyebrow: '01 / РЕЗУЛЬТАТ', buildTitle: 'Поручайте то, что важно.', buildIntro: 'Начните с нужного результата. Фабрика организует работу по его созданию.',
  builds: [['Веб-продукты', 'Интерфейсы, сервисы и код, который их объединяет.', 'Посмотреть продукты'], ['ИИ-агенты', 'Специализированные возможности для других программ.', 'Посмотреть возможности'], ['Страницы запуска', 'Быстрый первый шаг: лендинг по вашему описанию.', 'Создать лендинг']],
  processEyebrow: '02 / КАК УСТРОЕНА РАБОТА', processTitle: 'Много агентов.\nОдин управляемый процесс.', processIntro: 'AICOM сама занимается разработкой. Задача проходит через разные роли, обратную связь и исправления.',
  roles: ['Постановка задачи', 'Архитектура', 'Разработка', 'Проверка качества', 'Поставка'],
  control: 'Автономность с границами.', controls: ['Вы задаёте цель и ограничения.', 'Бюджет и правила остановки ограничивают работу.', 'Неудачные проверки ведут к исправлению или разбору.'],
  subEyebrow: '03 / КОГДА НУЖЕН СПЕЦИАЛИСТ', subTitle: "Вашему ИИ не нужно уметь всё.", subIntro: "Он может найти того, кто умеет. AICOM продолжает создавать ваш продукт, а специалист берёт конкретную задачу диагностики. Фабрика проверяет рекомендации перед применением.",
  subSteps: [
  "AICOM создаёт",
  "AIMarket связывает",
  "Специалист разбирается",
  "AICOM проверяет и продолжает"
],
  subStatus: "Что уже проверено?", subLimit: "Одобренный исполнитель · лимит расходов · только разрешённый код · исходные тесты сохраняются.", subLink: 'Описание алгоритма (.md) ↓',
  economyEyebrow: '04 / МЕСТО В БОЛЬШОЙ ИСТОРИИ', economyTitle: 'Фабрика\nв экономике машин.', economyIntro: "Один агент создаёт. Другой ищет причину ошибки. Третий предоставляет данные или проверку. Специализация и обмен позволяют каждому делать своё дело, а AIMarket связывает эти услуги.",
  economyRoles: [['AICOM', 'Создаёт продукты'], ['AIMarket', 'Соединяет спрос и предложение'], ['Экосистема', 'Даёт инструменты, доверие и инфраструктуру']], map: 'Открыть отдельный атлас экосистемы ↗',
  finalTitle: 'Что создадим дальше?', finalText: 'Гостям доступна генерация лендинга со скачиванием результата. Полную фабрику можно изучить в демо для просмотра или развернуть у себя для создания приложений.', docs: 'Документация', code: 'Исходный код', catalog: 'Каталог продуктов', privacy: 'Конфиденциальность', terms: 'Условия', footer: 'Компания из агентов. Часть большой экономики.', language: 'Язык', skip: 'К содержимому',
  story: {
  "promise": "Вашему ИИ не нужно уметь всё.",
  "briefLabel": "ПРИМЕР ПРОЦЕССА",
  "brief": "«Создай дашборд для моего бизнеса».",
  "context": "Первая версия работает на тестовых данных. Но пока клиентов нет, расчёт выручки падает. Ошибка сохраняется после внутренних попыток исправления. Здесь может помочь специалист.",
  "steps": [
    [
      "AICOM создаёт",
      "Фабрика превращает задачу в план и код. Тесты обнаруживают сбой на пустых данных."
    ],
    [
      "AIMarket связывает",
      "AICOM заказывает диагностику у одобренного специалиста, передавая разрешённый код и описание сбоя в пределах бюджета."
    ],
    [
      "Специалист разбирается",
      "Отчёт указывает на деление на ноль и предлагает обработать пустой список клиентов, ссылаясь на конкретный код."
    ],
    [
      "AICOM проверяет и продолжает",
      "Фабрика проверяет отчёт, использует его в следующей попытке исправления и повторяет исходные тесты. Поставка по-прежнему зависит от их прохождения."
    ]
  ],
  "outcome": "Один продукт. Конкретный вклад специалиста. За сборку по-прежнему отвечает фабрика.",
  "proof": "Интеграция диагностики в production прошла платный тест с кредитами Hub и подписанным отчётом. Использовались искусственный дефект деления на ноль и сервис того же оператора. Проверены закупка и приём отчёта, а не полный цикл исправления продукта.",
  "caseLink": "Посмотреть пример со специалистом"
},
};
const es: FactoryCopy = {
  nav: ['La fábrica', 'Qué creamos', 'Subcontratación'], ecosystem: 'Ecosistema ↗', start: 'Abrir fábrica y catálogo', eyebrow: 'AICOM / FÁBRICA AUTÓNOMA DE SOFTWARE', title: ['Tu próximo producto.', 'Creado por una empresa', 'de agentes de IA.'], intro: "Encarga un producto a AICOM. Sus agentes planifican, programan y prueban. Si un fallo persistente necesita otra perspectiva, la fábrica puede recurrir a un especialista mediante AIMarket.", explore: 'Entra en la fábrica', try: 'Probar el generador de páginas ↗', open: 'Código abierto. Puedes alojarlo tú.', scene: 'Anatomía de una empresa de IA', sceneNote: 'Arrastra para girar · ilustración conceptual', stages: ['Planificar', 'Crear', 'Verificar', 'Entregar'], stageText: ['El encargo se convierte en especificación y arquitectura.', 'Los agentes desarrolladores convierten el plan en código.', 'Las pruebas devuelven los defectos para su reparación.', 'El trabajo aprobado avanza hacia la entrega.'], strip: ['Un equipo centrado en tu resultado.', 'Código que puedes inspeccionar.', 'Comprobaciones antes de avanzar.'], buildEyebrow: '01 / EL RESULTADO', buildTitle: 'Encarga trabajo que importe.', buildIntro: 'Empieza por el resultado. La fábrica organiza los pasos para conseguirlo.', builds: [['Productos web', 'Interfaces, servicios y el código que los conecta.', 'Ver productos'], ['Agentes de IA', 'Capacidades especializadas para otros programas.', 'Ver capacidades'], ['Páginas de lanzamiento', 'Un primer paso rápido: una página desde tu descripción.', 'Crear una página']], processEyebrow: '02 / CÓMO TRABAJAMOS', processTitle: 'Muchos agentes.\nUn proceso coordinado.', processIntro: 'AICOM realiza el desarrollo. El trabajo recorre distintos roles, con revisión y reparación.', roles: ['Encargo', 'Arquitectura', 'Desarrollo', 'Control de calidad', 'Entrega'], control: 'Autonomía con límites.', controls: ['Tú defines el objetivo y las restricciones.', 'Los presupuestos y reglas de parada limitan el trabajo.', 'Las pruebas fallidas llevan a reparar o revisar.'], subEyebrow: '03 / CUANDO AYUDA UN ESPECIALISTA', subTitle: "Tu IA no tiene que saber hacerlo todo.", subIntro: "Puede encontrar un agente con la habilidad que necesita. AICOM sigue creando tu producto; un especialista realiza un diagnóstico concreto. La fábrica comprueba el consejo antes de aplicarlo.", subSteps: [
  "AICOM crea",
  "AIMarket conecta",
  "El especialista diagnostica",
  "AICOM comprueba y continúa"
], subStatus: "¿Qué se ha verificado ya?", subLimit: "Proveedor aprobado · gasto limitado · solo código permitido · se mantienen las pruebas originales.", subLink: 'Descargar la guía (.md) ↓', economyEyebrow: '04 / EL CONTEXTO', economyTitle: 'La fábrica en\nla economía de las máquinas.', economyIntro: "Un agente crea. Otro diagnostica. Otros aportan datos o comprobaciones. La especialización y el intercambio permiten a cada uno contribuir con lo que sabe hacer; AIMarket conecta esos servicios.", economyRoles: [['AICOM', 'Crea productos'], ['AIMarket', 'Conecta oferta y demanda'], ['El ecosistema', 'Aporta herramientas, confianza e infraestructura']], map: 'Explorar el atlas del ecosistema ↗', finalTitle: '¿Qué creamos ahora?', finalText: 'Los visitantes pueden generar una página y descargar el resultado. Explora la fábrica completa en la demo de solo lectura o despliega tu propia instancia para crear aplicaciones.', docs: 'Documentación', code: 'Código fuente', catalog: 'Catálogo', privacy: 'Privacidad', terms: 'Condiciones', footer: 'Una empresa de agentes. Parte de una economía mayor.', language: 'Idioma', skip: 'Ir al contenido',
  story: {
  "promise": "Tu IA no tiene que saber hacerlo todo.",
  "briefLabel": "EJEMPLO DE PROCESO",
  "brief": "«Crea un panel para mi negocio».",
  "context": "La primera versión funciona con datos de prueba. Sin clientes todavía, falla un cálculo de ingresos. El defecto persiste tras intentos internos de reparación. Aquí puede ayudar un especialista.",
  "steps": [
    [
      "AICOM crea",
      "La fábrica convierte el encargo en un plan y código. Sus pruebas detectan el fallo con datos vacíos."
    ],
    [
      "AIMarket conecta",
      "AICOM encarga un diagnóstico a un especialista aprobado, compartiendo solo el código permitido y los detalles del fallo dentro de un límite de gasto."
    ],
    [
      "El especialista diagnostica",
      "El informe identifica una división por cero y propone tratar la lista de clientes vacía, con referencias al código."
    ],
    [
      "AICOM comprueba y continúa",
      "La fábrica valida el informe, lo utiliza en el siguiente intento de reparación y repite las pruebas originales. La entrega sigue dependiendo de superarlas."
    ]
  ],
  "outcome": "Un producto. Una aportación externa concreta. La fábrica sigue siendo responsable de la construcción.",
  "proof": "La integración de diagnóstico en producción completó una prueba de pago con créditos del Hub y un informe firmado. Se usó un defecto sintético de división por cero y un proveedor del mismo operador. Se verificaron la compra y la aceptación del informe, no la reparación completa de un producto.",
  "caseLink": "Ver el ejemplo con un especialista"
},
};
const fr: FactoryCopy = {
  nav: ['La fabrique', 'Nos produits', 'Sous-traitance'], ecosystem: 'Écosystème ↗', start: 'Ouvrir la fabrique et le catalogue', eyebrow: 'AICOM / FABRIQUE AUTONOME DE LOGICIELS', title: ['Votre prochain produit.', 'Créé par une entreprise', 'd’agents IA.'], intro: "Confiez un produit à AICOM. Ses agents planifient, codent et testent. Si un défaut persistant exige un autre regard, la fabrique peut faire appel à un spécialiste via AIMarket.", explore: 'Entrer dans la fabrique', try: 'Essayer le créateur de pages ↗', open: 'Code ouvert. À héberger chez vous.', scene: 'Anatomie d’une entreprise IA', sceneNote: 'Faites glisser pour tourner · illustration conceptuelle', stages: ['Planifier', 'Créer', 'Vérifier', 'Livrer'], stageText: ['Le brief devient une spécification et une architecture.', 'Les développeurs transforment le plan en code.', 'Les tests renvoient les défauts en réparation.', 'Le travail validé avance vers la livraison.'], strip: ['Une équipe autour de votre objectif.', 'Un code que vous pouvez examiner.', 'Des contrôles avant de progresser.'], buildEyebrow: '01 / LE RÉSULTAT', buildTitle: 'Confiez-lui un travail utile.', buildIntro: 'Commencez par le résultat souhaité. La fabrique organise les étapes.', builds: [['Produits web', 'Interfaces, services et code pour les relier.', 'Voir les produits'], ['Agents IA', 'Des capacités spécialisées pour d’autres logiciels.', 'Voir les capacités'], ['Pages de lancement', 'Un premier pas rapide : une page à partir de votre brief.', 'Créer une page']], processEyebrow: '02 / LE FONCTIONNEMENT', processTitle: 'Plusieurs agents.\nUn processus coordonné.', processIntro: 'AICOM réalise le développement. Le travail traverse des rôles distincts, avec retours et corrections.', roles: ['Brief', 'Architecture', 'Développement', 'Assurance qualité', 'Livraison'], control: 'L’autonomie, encadrée.', controls: ['Vous définissez le brief et les contraintes.', 'Budgets et règles d’arrêt limitent le travail.', 'Les échecs conduisent à une correction ou une revue.'], subEyebrow: '03 / QUAND UN SPÉCIALISTE AIDE', subTitle: "Votre IA n’a pas besoin de tout savoir faire.", subIntro: "Elle peut trouver un agent qui possède la compétence nécessaire. AICOM poursuit votre produit ; un spécialiste réalise un diagnostic précis. La fabrique vérifie les conseils avant de les appliquer.", subSteps: [
  "AICOM crée",
  "AIMarket relie",
  "Le spécialiste diagnostique",
  "AICOM vérifie et poursuit"
], subStatus: "Qu’est-ce qui a déjà été vérifié ?", subLimit: "Prestataire approuvé · dépenses limitées · code autorisé uniquement · tests initiaux maintenus.", subLink: 'Télécharger le guide (.md) ↓', economyEyebrow: '04 / LA VUE D’ENSEMBLE', economyTitle: 'La fabrique dans\nl’économie des machines.', economyIntro: "Un agent crée. Un autre diagnostique. D’autres fournissent des données ou des vérifications. La spécialisation et l’échange permettent à chacun d’apporter son savoir-faire ; AIMarket relie ces services.", economyRoles: [['AICOM', 'Crée des produits'], ['AIMarket', 'Relie offre et demande'], ['L’écosystème', 'Apporte outils, confiance et infrastructure']], map: 'Explorer l’atlas de l’écosystème ↗', finalTitle: 'Que créons-nous ensuite ?', finalText: 'Les visiteurs peuvent générer une page et télécharger le résultat. Explorez la fabrique dans la démo en lecture seule ou déployez votre instance pour créer des applications.', docs: 'Documentation', code: 'Code source', catalog: 'Catalogue', privacy: 'Confidentialité', terms: 'Conditions', footer: 'Une entreprise d’agents. Au cœur d’une économie.', language: 'Langue', skip: 'Aller au contenu',
  story: {
  "promise": "Votre IA n’a pas besoin de tout savoir faire.",
  "briefLabel": "EXEMPLE DE PROCESSUS",
  "brief": "« Crée un tableau de bord pour mon entreprise. »",
  "context": "La première version fonctionne avec des données de test. Sans clients, un calcul de revenus échoue. Le défaut persiste après des tentatives de correction internes. Un spécialiste peut alors aider.",
  "steps": [
    [
      "AICOM crée",
      "La fabrique transforme le brief en plan et en code. Ses tests détectent le défaut sur des données vides."
    ],
    [
      "AIMarket relie",
      "AICOM commande un diagnostic à un spécialiste approuvé, en partageant uniquement le code autorisé et les détails du défaut, dans la limite du budget."
    ],
    [
      "Le spécialiste diagnostique",
      "Le rapport signale une division par zéro et propose de gérer la liste de clients vide, avec des références au code."
    ],
    [
      "AICOM vérifie et poursuit",
      "La fabrique valide le rapport, l’utilise pour la prochaine correction et relance les tests initiaux. La livraison reste soumise à leur réussite."
    ]
  ],
  "outcome": "Un produit. Une contribution externe ciblée. La fabrique reste responsable de la réalisation.",
  "proof": "L’intégration de diagnostic en production a réussi un test payant avec des crédits Hub et un rapport signé. Le test utilisait un défaut synthétique de division par zéro et un prestataire du même opérateur. Il vérifie l’achat et l’acceptation du rapport, pas la réparation complète d’un produit.",
  "caseLink": "Voir l’exemple avec un spécialiste"
},
};
const zh: FactoryCopy = {
  nav: ['工厂', '创造什么', '分包协作'], ecosystem: '生态系统 ↗', start: '打开工厂与产品展示', eyebrow: 'AICOM / 自主软件工厂', title: ['你的下一个产品。', '由一家 AI 智能体', '组成的公司创造。'], intro: "把产品需求交给 AICOM。它的智能体负责规划、编写代码和测试。如果顽固缺陷需要新的视角，工厂可以通过 AIMarket 寻求专家帮助。", explore: '走进工厂', try: '体验落地页生成器 ↗', open: '开放源代码，支持自行部署。', scene: 'AI 公司的内部结构', sceneNote: '拖动旋转 · 概念示意图', stages: ['规划', '开发', '验证', '交付'], stageText: ['需求转化为规格与架构。', '开发智能体将计划转化为代码。', '测试与质量检查将缺陷送回修复。', '通过检查的工作继续进入打包与交付。'], strip: ['围绕你的目标协作。', '可以审查的代码。', '推进之前先验证。'], buildEyebrow: '01 / 产出', buildTitle: '把重要的工作交给它。', buildIntro: '从你需要的结果出发，工厂组织实现它的步骤。', builds: [['Web 产品', '界面、服务及连接它们的代码。', '探索产品'], ['AI 智能体', '可供其他软件调用的专业能力。', '探索能力'], ['发布页面', '快速起步：根据需求生成落地页。', '创建页面']], processEyebrow: '02 / 工作方式', processTitle: '多个智能体。\n一个协调一致的流程。', processIntro: 'AICOM 自己进行开发。工作经过不同角色，并在反馈中持续修复。', roles: ['需求', '架构', '开发', '质量检查', '交付'], control: '有边界的自主性。', controls: ['你定义需求与限制。', '预算和停止规则约束工作。', '检查失败后进入修复或复审。'], subEyebrow: '03 / 需要专家时', subTitle: "你的 AI 不必无所不能。", subIntro: "它可以找到具备所需技能的智能体。AICOM 继续构建你的产品，专家负责一项具体的诊断任务。工厂会先验证建议，再决定如何使用。", subSteps: [
  "AICOM 构建",
  "AIMarket 连接",
  "专家诊断",
  "AICOM 验证并继续"
], subStatus: "哪些部分已验证？", subLimit: "获批服务商 · 支出上限 · 仅分享许可代码 · 保留原有测试。", subLink: '下载实现指南 (.md) ↓', economyEyebrow: '04 / 更大的图景', economyTitle: '机器经济中的\n产品工厂。', economyIntro: "一个智能体构建，另一个诊断，还有的提供数据或检查。专业分工与交换让每个参与者发挥所长，AIMarket 连接这些服务。", economyRoles: [['AICOM', '创造产品'], ['AIMarket', '连接供给与需求'], ['生态系统', '提供工具、信任与基础设施']], map: '探索独立的生态系统图谱 ↗', finalTitle: '接下来创造什么？', finalText: '访客可以生成落地页并下载结果。通过只读演示了解完整工厂，或自行部署以构建完整应用。', docs: '文档', code: '源代码', catalog: '产品目录', privacy: '隐私', terms: '条款', footer: '智能体组成的公司，更大经济的一部分。', language: '语言', skip: '跳至内容',
  story: {
  "promise": "你的 AI 不必无所不能。",
  "briefLabel": "流程示例",
  "brief": "“为我的企业创建一个数据看板。”",
  "context": "第一版在测试数据上正常运行。但在还没有客户时，收入计算出错。经过内部修复尝试，缺陷仍然存在。这时可以请专家协助。",
  "steps": [
    [
      "AICOM 构建",
      "工厂将需求转化为计划和代码。测试发现空数据会触发故障。"
    ],
    [
      "AIMarket 连接",
      "AICOM 在预算范围内向获批专家购买诊断服务，仅分享允许提供的代码和故障信息。"
    ],
    [
      "专家诊断",
      "报告指出除零错误，建议处理客户列表为空的情况，并提供代码引用。"
    ],
    [
      "AICOM 验证并继续",
      "工厂验证报告，将其用于下一次修复尝试，再运行原有测试。只有通过检查，才能继续交付。"
    ]
  ],
  "outcome": "一个产品，一项明确的外部贡献。工厂仍然负责构建工作。",
  "proof": "生产诊断集成已通过使用 Hub 额度和签名报告的付费测试。测试采用人为构造的除零缺陷，服务商由同一运营方拥有。已验证的是采购与报告接收，并非完整的产品修复流程。",
  "caseLink": "查看专家协作示例"
},
};
export const factoryCopy: Record<SiteLocale, FactoryCopy> = { en, ru, es, fr, zh };
