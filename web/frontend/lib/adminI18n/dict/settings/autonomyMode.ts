import type { I18nDict } from '../../types';

export const AUTONOMY_MODE_SETTINGS_DICT: I18nDict = {
  'settings.autonomyMode.title': {
    en: 'Full autonomy',
    ru: 'Полная автономия',
    es: 'Autonomía total',
  },
  'settings.autonomyMode.bodyFull': {
    en: 'Human gates are resolved by the AI surrogate (heavy judge model). The pipeline never parks waiting for an operator.',
    ru: 'Человеческие гейты закрывает AI-суррогат (тяжёлая judge-модель). Пайплайн не ждёт оператора.',
    es: 'Las compuertas humanas las resuelve el sustituto IA (modelo juez pesado). El pipeline no espera al operador.',
  },
  'settings.autonomyMode.bodySupervised': {
    en: 'Supervised mode — human gates block until an admin approves (default, unchanged behavior).',
    ru: 'Supervised — гейты блокируют пайплайн до одобрения админом (поведение по умолчанию).',
    es: 'Modo supervisado: las compuertas humanas bloquean hasta aprobación del admin (comportamiento por defecto).',
  },
  'settings.autonomyMode.hint': {
    en: 'Hard policy gates (benchmark, Critical security, demo/smoke pass/fail) are never auto-waived.',
    ru: 'Жёсткие гейты (benchmark, Critical security, demo/smoke) никогда не обходятся автоматически.',
    es: 'Las compuertas de política dura (benchmark, seguridad crítica, demo/smoke) nunca se omiten automáticamente.',
  },
  'settings.autonomyMode.demoNote': {
    en: 'Demo mode: toggle is saved but factory runs read-only.',
    ru: 'Демо: переключатель сохраняется, фабрика в read-only.',
    es: 'Modo demo: el interruptor se guarda pero la fábrica es de solo lectura.',
  },
  'settings.autonomyMode.labelFull': {
    en: 'Full',
    ru: 'Full',
    es: 'Full',
  },
  'settings.autonomyMode.labelSupervised': {
    en: 'Supervised',
    ru: 'Supervised',
    es: 'Supervised',
  },
  'settings.autonomyMode.ariaFull': {
    en: 'Enable full autonomy',
    ru: 'Включить полную автономию',
    es: 'Activar autonomía total',
  },
  'settings.autonomyMode.ariaSupervised': {
    en: 'Return to supervised mode',
    ru: 'Вернуть supervised режим',
    es: 'Volver al modo supervisado',
  },
  'settings.autonomyMode.requiresAutoDev': {
    en: 'Available when autonomous development is on — AI surrogate replaces human gates on the pipeline.',
    ru: 'Доступно при включённой автономной разработке — AI-суррогат закрывает человеческие гейты пайплайна.',
    es: 'Disponible con desarrollo autónomo activo — el sustituto IA reemplaza las compuertas humanas del pipeline.',
  },
  'settings.toast.autonomyRequiresAutoDev': {
    en: 'Full autonomy requires autonomous development to be enabled',
    ru: 'Полная автономия доступна только при включённой автономной разработке',
    es: 'La autonomía total requiere desarrollo autónomo activado',
  },
  'settings.toast.autonomyFull': {
    en: 'Full autonomy enabled — AI surrogate resolves human gates',
    ru: 'Полная автономия — гейты закрывает AI-суррогат',
    es: 'Autonomía total activada — el sustituto IA resuelve las compuertas humanas',
  },
  'settings.toast.autonomySupervised': {
    en: 'Supervised mode — human approval required at gates',
    ru: 'Supervised — на гейтах нужно одобрение человека',
    es: 'Modo supervisado — se requiere aprobación humana en las compuertas',
  },
};
