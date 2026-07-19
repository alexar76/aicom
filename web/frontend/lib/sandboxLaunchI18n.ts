/** Shared sandbox launch overlay strings (storefront + admin). */

export type SandboxLaunchLocale = 'en' | 'ru' | 'es';

const LABELS = {
  title: {
    en: 'Preparing preview',
    ru: 'Подготовка превью',
    es: 'Preparando vista previa',
  },
  starting: {
    en: 'Starting…',
    ru: 'Запуск…',
    es: 'Iniciando…',
  },
  startingSandbox: {
    en: 'Starting sandbox…',
    ru: 'Запуск песочницы…',
    es: 'Iniciando sandbox…',
  },
  preparingCode: {
    en: 'Preparing product code…',
    ru: 'Подготовка кода продукта…',
    es: 'Preparando código del producto…',
  },
  buildingPreview: {
    en: 'Building preview…',
    ru: 'Сборка превью…',
    es: 'Generando vista previa…',
  },
  loadingLanding: {
    en: 'Loading landing page…',
    ru: 'Загрузка лендинга…',
    es: 'Cargando landing…',
  },
  done: {
    en: 'Ready',
    ru: 'Готово',
    es: 'Listo',
  },
  openingPreview: {
    en: 'Opening preview…',
    ru: 'Открываем превью…',
    es: 'Abriendo vista previa…',
  },
  heavyStackWarning: {
    en: 'Full stack may take several minutes — please wait…',
    ru: 'Полный стек может собираться несколько минут — подождите…',
    es: 'El stack completo puede tardar varios minutos…',
  },
  degradedPreview: {
    en: 'Reduced preview (static only — server low on disk/memory)',
    ru: 'Урезанное превью (только статика — мало места или памяти на сервере)',
    es: 'Vista previa reducida (solo estática — poco disco o memoria)',
  },
  bootstrapping: {
    en: 'Building Docker stack & API…',
    ru: 'Сборка Docker-стека и API…',
    es: 'Construyendo stack Docker y API…',
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
  return 'en';
}
