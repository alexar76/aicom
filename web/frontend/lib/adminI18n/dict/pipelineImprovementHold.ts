import type { I18nDict } from '../types';

export const PIPELINE_IMPROVEMENT_HOLD_DICT: I18nDict = {
  'pipeline.improvementHold.title': {
    en: 'Improvement hold',
    ru: 'Пауза улучшений',
    es: 'Pausa de mejoras',
    fr: 'Suspension des améliorations',
    zh: '改进暂停',
  },
  'pipeline.improvementHold.helpOn': {
    en: 'Automatic monitoring, refactor, and storefront remediation are paused for this product.',
    ru: 'Авто-мониторинг, рефакторинг и доработка витрины для этого продукта приостановлены.',
    es: 'Monitoreo automático, refactor y remediación de tienda pausados para este producto.',
    fr: 'La surveillance automatique, le refactoring et la correction de la vitrine sont suspendus pour ce produit.',
    zh: '该产品的自动监控、重构和店面修复已暂停。',
  },
  'pipeline.improvementHold.helpOff': {
    en: 'Continuous improvements are allowed (monitoring, refactor, remediation).',
    ru: 'Непрерывные улучшения разрешены (мониторинг, рефакторинг, доработка).',
    es: 'Mejoras continuas permitidas (monitoreo, refactor, remediación).',
    fr: 'Les améliorations continues sont autorisées (surveillance, refactoring, correction).',
    zh: '允许持续改进（监控、重构、修复）。',
  },
  'pipeline.improvementHold.badge': {
    en: 'Hold',
    ru: 'Пауза',
    es: 'Pausa',
    fr: 'Suspendu',
    zh: '暂停',
  },
  'pipeline.improvementHold.statusOn': {
    en: 'On hold',
    ru: 'На паузе',
    es: 'En pausa',
    fr: 'En pause',
    zh: '已暂停',
  },
  'pipeline.improvementHold.statusOff': {
    en: 'Active',
    ru: 'Активно',
    es: 'Activo',
    fr: 'Actif',
    zh: '进行中',
  },
  'pipeline.improvementHold.toastOn': {
    en: 'Improvement hold enabled for this product',
    ru: 'Пауза улучшений включена для продукта',
    es: 'Pausa de mejoras activada para este producto',
    fr: 'Suspension des améliorations activée pour ce produit',
    zh: '已为该产品启用改进暂停',
  },
  'pipeline.improvementHold.toastOff': {
    en: 'Continuous improvements resumed',
    ru: 'Непрерывные улучшения снова включены',
    es: 'Mejoras continuas reanudadas',
    fr: 'Améliorations continues reprises',
    zh: '已恢复持续改进',
  },
  'pipeline.improvementHold.toastFailed': {
    en: 'Could not update improvement hold',
    ru: 'Не удалось обновить паузу улучшений',
    es: 'No se pudo actualizar la pausa de mejoras',
    fr: 'Impossible de mettre à jour la suspension des améliorations',
    zh: '无法更新改进暂停',
  },
};
