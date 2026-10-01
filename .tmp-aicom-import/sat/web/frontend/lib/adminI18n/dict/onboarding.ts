import type { I18nDict } from '../types';

export const ONBOARDING_DICT: I18nDict = {
  'onboarding.title': { en: 'Get oriented in three moves', ru: 'Три шага для старта', es: 'Orientación en tres pasos', fr: 'S\'orienter en trois étapes', zh: '三步快速上手' },
  'onboarding.firstInstall': {
    en: 'First install? Run the Setup wizard (URLs + one LLM key) — then continue below.',
    ru: 'Первый запуск? Пройдите мастер настройки (URL + ключ LLM) — затем шаги ниже.',
    es: '¿Primera instalación? Ejecute el asistente (URLs + clave LLM) y continúe abajo.',
    fr: 'Première installation ? Lancez l\'assistant de configuration (URLs + une clé LLM) — puis continuez ci-dessous.',
    zh: '首次安装？运行设置向导（URL + 一个 LLM 密钥）—— 然后继续下方步骤。',
  },
  'onboarding.setupWizard': { en: 'Setup wizard', ru: 'Мастер настройки', es: 'Asistente de configuración', fr: 'Assistant de configuration', zh: '设置向导' },
  'onboarding.step1': {
    en: 'See health first — open Dashboard for queue depth and alerts.',
    ru: 'Сначала здоровье — откройте «Дашборд» для очереди и алертов.',
    es: 'Primero salud — abra Panel para cola y alertas.',
    fr: 'Vérifiez d\'abord l\'état — ouvrez Tableau de bord pour la profondeur de file et les alertes.',
    zh: '先看运行状况 —— 打开仪表板查看队列深度和告警。',
  },
  'onboarding.step2': {
    en: 'Queue real work — New product walks idea → options → review; save presets as local or cloud templates.',
    ru: 'Поставьте работу в очередь — «Новый продукт»: идея → опции → проверка; шаблоны локально или в облаке.',
    es: 'Encole trabajo real — Nuevo producto: idea → opciones → revisión; plantillas locales o en la nube.',
    fr: 'Mettez du vrai travail en file — Nouveau produit déroule idée → options → revue ; enregistrez des préréglages en modèles locaux ou cloud.',
    zh: '将真实工作排入队列 —— 新产品引导 想法 → 选项 → 评审；将预设保存为本地或云端模板。',
  },
  'onboarding.step3': {
    en: 'Wire models once — Providers and Settings so agents do not fail silently.',
    ru: 'Подключите модели один раз — «Провайдеры» и «Настройки», чтобы агенты не падали молча.',
    es: 'Configure modelos una vez — Proveedores y Ajustes para que los agentes no fallen en silencio.',
    fr: 'Configurez les modèles une fois — Fournisseurs et Paramètres pour que les agents n\'échouent pas en silence.',
    zh: '一次性接好模型 —— 提供商和设置，让智能体不再静默失败。',
  },
  'onboarding.failHint': {
    en: 'When something fails, look for retry plus links to Providers or Pipeline on the error card.',
    ru: 'При ошибке ищите «Повтор» и ссылки на «Провайдеры» или «Пайплайн» на карточке.',
    es: 'Si falla algo, busque reintentar y enlaces a Proveedores o Pipeline en la tarjeta.',
    fr: 'En cas d\'échec, cherchez le bouton réessayer et les liens vers Fournisseurs ou Pipeline sur la carte d\'erreur.',
    zh: '出错时，在错误卡片上查找重试按钮以及指向提供商或 Pipeline 的链接。',
  },
  'onboarding.newProduct': { en: 'New product', ru: 'Новый продукт', es: 'Nuevo producto', fr: 'Nouveau produit', zh: '新产品' },
  'onboarding.workshop': { en: 'Workshop tools', ru: 'Мастерская', es: 'Taller', fr: 'Outils d\'atelier', zh: '工坊工具' },
  'onboarding.dismiss': { en: 'Dismiss onboarding', ru: 'Скрыть подсказки', es: 'Ocultar onboarding', fr: 'Masquer l\'accueil', zh: '关闭引导' },
  'onboarding.onNewProductTab': {
    en: 'You are on New product: use the left guide column for what each step expects, then apply a quick-start chip if you want a filled example idea.',
    ru: 'Вы на «Новый продукт»: слева подсказки по шагам; можно взять быстрый шаблон с примером идеи.',
    es: 'Está en Nuevo producto: guía a la izquierda; use una plantilla rápida con idea de ejemplo.',
    fr: 'Vous êtes sur Nouveau produit : utilisez la colonne guide de gauche pour savoir ce qu\'attend chaque étape, puis appliquez une puce de démarrage rapide pour une idée d\'exemple préremplie.',
    zh: '你正处于新产品页：使用左侧指南栏了解每一步的要求，然后点选快速开始标签以获得预填的示例想法。',
  },
};
