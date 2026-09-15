/** Shared sandbox launch overlay strings (storefront + admin). */

export type SandboxLaunchLocale = 'en' | 'ru' | 'es' | 'fr' | 'zh';

const LABELS = {
  title: {
    en: 'Preparing preview',
    ru: 'Подготовка превью',
    es: 'Preparando vista previa',
    fr: 'Préparation de l’aperçu',
    zh: '正在准备预览',
  },
  starting: {
    en: 'Starting…',
    ru: 'Запуск…',
    es: 'Iniciando…',
    fr: 'Démarrage…',
    zh: '正在启动…',
  },
  startingSandbox: {
    en: 'Starting sandbox…',
    ru: 'Запуск песочницы…',
    es: 'Iniciando sandbox…',
    fr: 'Démarrage du bac à sable…',
    zh: '正在启动沙箱…',
  },
  preparingCode: {
    en: 'Preparing product code…',
    ru: 'Подготовка кода продукта…',
    es: 'Preparando código del producto…',
    fr: 'Préparation du code du produit…',
    zh: '正在准备产品代码…',
  },
  buildingPreview: {
    en: 'Building preview…',
    ru: 'Сборка превью…',
    es: 'Generando vista previa…',
    fr: 'Construction de l’aperçu…',
    zh: '正在构建预览…',
  },
  loadingLanding: {
    en: 'Loading landing page…',
    ru: 'Загрузка лендинга…',
    es: 'Cargando landing…',
    fr: 'Chargement de la landing…',
    zh: '正在加载着陆页…',
  },
  done: {
    en: 'Ready',
    ru: 'Готово',
    es: 'Listo',
    fr: 'Prêt',
    zh: '就绪',
  },
  openingPreview: {
    en: 'Opening preview…',
    ru: 'Открываем превью…',
    es: 'Abriendo vista previa…',
    fr: 'Ouverture de l’aperçu…',
    zh: '正在打开预览…',
  },
  heavyStackWarning: {
    en: 'Full stack may take several minutes — please wait…',
    ru: 'Полный стек может собираться несколько минут — подождите…',
    es: 'El stack completo puede tardar varios minutos…',
    fr: 'La stack complète peut prendre plusieurs minutes — patientez…',
    zh: '完整技术栈可能需要几分钟——请稍候…',
  },
  degradedPreview: {
    en: 'Reduced preview (static only — server low on disk/memory)',
    ru: 'Урезанное превью (только статика — мало места или памяти на сервере)',
    es: 'Vista previa reducida (solo estática — poco disco o memoria)',
    fr: 'Aperçu réduit (statique seulement — serveur à court de disque/mémoire)',
    zh: '精简预览（仅静态——服务器磁盘/内存不足）',
  },
  bootstrapping: {
    en: 'Building Docker stack & API…',
    ru: 'Сборка Docker-стека и API…',
    es: 'Construyendo stack Docker y API…',
    fr: 'Construction de la stack Docker et de l’API…',
    zh: '正在构建 Docker 技术栈与 API…',
  },
} as const;

export type SandboxLaunchLabelKey = keyof typeof LABELS;

export function sandboxLaunchLabel(
  locale: SandboxLaunchLocale | string | null | undefined,
  key: SandboxLaunchLabelKey,
): string {
  const loc = normalizeSandboxLaunchLocale(locale);
  return LABELS[key][loc];
}

export function normalizeSandboxLaunchLocale(
  locale: SandboxLaunchLocale | string | null | undefined,
): SandboxLaunchLocale {
  const raw = (locale || '').toLowerCase();
  if (raw.startsWith('ru')) return 'ru';
  if (raw.startsWith('es')) return 'es';
  if (raw.startsWith('fr')) return 'fr';
  if (raw.startsWith('zh')) return 'zh';
  return 'en';
}
