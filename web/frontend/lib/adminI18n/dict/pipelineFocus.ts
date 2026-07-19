import type { I18nDict } from '../types';

export const PIPELINE_FOCUS_DICT: I18nDict = {
  'pipeline.focus.title': {
    en: 'Focus mode',
    ru: 'Режим фокуса',
    es: 'Modo enfoque',
  },
  'pipeline.focus.helpActive': {
    en: 'Factory runs, but only the focused product receives pipeline agent work. All others are paused.',
    ru: 'Фабрика работает, но агенты занимаются только выбранным продуктом. Остальные на паузе.',
    es: 'La fábrica corre, pero solo el producto enfocado recibe trabajo de agentes. Los demás están en pausa.',
  },
  'pipeline.focus.helpInactive': {
    en: 'Pause every product except one complex build and drive it to completion.',
    ru: 'Поставьте на паузу все продукты кроме одного сложного и доведите его до конца.',
    es: 'Pausa todos los productos excepto uno complejo y llévalo hasta el final.',
  },
  'pipeline.focus.selectLabel': {
    en: 'Focus product',
    ru: 'Продукт в фокусе',
    es: 'Producto en foco',
  },
  'pipeline.focus.autoSelect': {
    en: 'Pick most complex',
    ru: 'Выбрать самый сложный',
    es: 'Elegir el más complejo',
  },
  'pipeline.focus.enable': {
    en: 'Enable focus',
    ru: 'Включить фокус',
    es: 'Activar enfoque',
  },
  'pipeline.focus.disable': {
    en: 'Clear focus',
    ru: 'Снять фокус',
    es: 'Quitar enfoque',
  },
  'pipeline.focus.badge': {
    en: 'Focus',
    ru: 'Фокус',
    es: 'Foco',
  },
  'pipeline.focus.pausedCount': {
    en: '{paused} paused · {active} active',
    ru: '{paused} на паузе · {active} активных',
    es: '{paused} en pausa · {active} activos',
  },
  'pipeline.focus.toastEnabled': {
    en: 'Focus mode enabled',
    ru: 'Режим фокуса включён',
    es: 'Modo enfoque activado',
  },
  'pipeline.focus.toastDisabled': {
    en: 'Focus mode cleared — all products can run',
    ru: 'Фокус снят — все продукты снова могут работать',
    es: 'Enfoque quitado — todos los productos pueden ejecutarse',
  },
  'pipeline.focus.toastFailed': {
    en: 'Could not update focus mode',
    ru: 'Не удалось обновить режим фокуса',
    es: 'No se pudo actualizar el modo enfoque',
  },
  'pipeline.focus.globalBanner': {
    en: 'Focus mode: only {productId} is active — {paused} other product(s) paused.',
    ru: 'Режим фокуса: активен только {productId} — {paused} других на паузе.',
    es: 'Modo enfoque: solo {productId} activo — {paused} producto(s) en pausa.',
  },
  'pipeline.focus.openPipeline': {
    en: 'Open Pipeline → Focus',
    ru: 'Открыть Pipeline → Фокус',
    es: 'Abrir Pipeline → Foco',
  },
  'pipeline.pipelineHold.title': {
    en: 'Pipeline hold',
    ru: 'Пауза пайплайна',
    es: 'Pausa de pipeline',
  },
  'pipeline.pipelineHold.helpOn': {
    en: 'All pipeline agent work is paused for this product (repair, QA, deploy).',
    ru: 'Весь пайплайн для этого продукта на паузе (ремонт, QA, деплой).',
    es: 'Todo el trabajo de pipeline está en pausa para este producto.',
  },
  'pipeline.pipelineHold.helpOff': {
    en: 'Pipeline agents may start and continue tasks for this product.',
    ru: 'Агенты могут запускать и продолжать задачи для этого продукта.',
    es: 'Los agentes pueden iniciar y continuar tareas para este producto.',
  },
  'pipeline.pipelineHold.badge': {
    en: 'Pipeline paused',
    ru: 'Пайплайн на паузе',
    es: 'Pipeline en pausa',
  },
  'pipeline.pipelineHold.toastOn': {
    en: 'Pipeline hold enabled',
    ru: 'Пауза пайплайна включена',
    es: 'Pausa de pipeline activada',
  },
  'pipeline.pipelineHold.toastOff': {
    en: 'Pipeline work resumed',
    ru: 'Пайплайн снова активен',
    es: 'Pipeline reanudado',
  },
  'pipeline.pipelineHold.toastFailed': {
    en: 'Could not update pipeline hold',
    ru: 'Не удалось обновить паузу пайплайна',
    es: 'No se pudo actualizar la pausa de pipeline',
  },
  'pipeline.filter.deliveryAll': {
    en: 'All delivery profiles',
    ru: 'Все профили доставки',
    es: 'Todos los perfiles',
  },
  'pipeline.filter.deliveryFullSoftware': {
    en: 'Full software',
    ru: 'Full software',
    es: 'Software completo',
  },
  'pipeline.filter.deliveryMarketingLanding': {
    en: 'Marketing landing',
    ru: 'Marketing landing',
    es: 'Landing de marketing',
  },
  'pipeline.filter.deliveryLandingFast': {
    en: 'Landing fast',
    ru: 'Landing fast',
    es: 'Landing rápido',
  },
  'pipeline.filter.workAll': {
    en: 'All work states',
    ru: 'Все статусы работы',
    es: 'Todos los estados',
  },
  'pipeline.filter.workActive': {
    en: 'Active pipeline',
    ru: 'Активный пайплайн',
    es: 'Pipeline activo',
  },
  'pipeline.filter.workPaused': {
    en: 'Paused pipeline',
    ru: 'Пайплайн на паузе',
    es: 'Pipeline en pausa',
  },
  'pipeline.filter.workFocus': {
    en: 'In focus',
    ru: 'В фокусе',
    es: 'En foco',
  },
  'pipeline.filter.repairAll': {
    en: 'Any repair round',
    ru: 'Любой repair round',
    es: 'Cualquier ronda de reparación',
  },
  'pipeline.filter.repairMin': {
    en: 'Repair round ≥ {n}',
    ru: 'Repair round ≥ {n}',
    es: 'Ronda de reparación ≥ {n}',
  },
};
