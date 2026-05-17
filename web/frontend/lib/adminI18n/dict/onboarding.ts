import type { I18nDict } from '../types';

export const ONBOARDING_DICT: I18nDict = {
  'onboarding.title': { en: 'Get oriented in three moves', ru: 'Три шага для старта', es: 'Orientación en tres pasos' },
  'onboarding.firstInstall': {
    en: 'First install? Run the Setup wizard (URLs + one LLM key) — then continue below.',
    ru: 'Первый запуск? Пройдите мастер настройки (URL + ключ LLM) — затем шаги ниже.',
    es: '¿Primera instalación? Ejecute el asistente (URLs + clave LLM) y continúe abajo.',
  },
  'onboarding.setupWizard': { en: 'Setup wizard', ru: 'Мастер настройки', es: 'Asistente de configuración' },
  'onboarding.step1': {
    en: 'See health first — open Dashboard for queue depth and alerts.',
    ru: 'Сначала здоровье — откройте «Дашборд» для очереди и алертов.',
    es: 'Primero salud — abra Panel para cola y alertas.',
  },
  'onboarding.step2': {
    en: 'Queue real work — New product walks idea → options → review; save presets as local or cloud templates.',
    ru: 'Поставьте работу в очередь — «Новый продукт»: идея → опции → проверка; шаблоны локально или в облаке.',
    es: 'Encole trabajo real — Nuevo producto: idea → opciones → revisión; plantillas locales o en la nube.',
  },
  'onboarding.step3': {
    en: 'Wire models once — Providers and Settings so agents do not fail silently.',
    ru: 'Подключите модели один раз — «Провайдеры» и «Настройки», чтобы агенты не падали молча.',
    es: 'Configure modelos una vez — Proveedores y Ajustes para que los agentes no fallen en silencio.',
  },
  'onboarding.failHint': {
    en: 'When something fails, look for retry plus links to Providers or Pipeline on the error card.',
    ru: 'При ошибке ищите «Повтор» и ссылки на «Провайдеры» или «Пайплайн» на карточке.',
    es: 'Si falla algo, busque reintentar y enlaces a Proveedores o Pipeline en la tarjeta.',
  },
  'onboarding.newProduct': { en: 'New product', ru: 'Новый продукт', es: 'Nuevo producto' },
  'onboarding.workshop': { en: 'Workshop tools', ru: 'Мастерская', es: 'Taller' },
  'onboarding.dismiss': { en: 'Dismiss onboarding', ru: 'Скрыть подсказки', es: 'Ocultar onboarding' },
  'onboarding.onNewProductTab': {
    en: 'You are on New product: use the left guide column for what each step expects, then apply a quick-start chip if you want a filled example idea.',
    ru: 'Вы на «Новый продукт»: слева подсказки по шагам; можно взять быстрый шаблон с примером идеи.',
    es: 'Está en Nuevo producto: guía a la izquierda; use una plantilla rápida con idea de ejemplo.',
  },
};
