import type { I18nDict } from '../../types';

export const FACTORY_HOLD_SETTINGS_DICT: I18nDict = {
  'settings.factoryHold.title': {
    en: 'Factory hold',
    ru: 'Пауза фабрики',
    es: 'Pausa de la fábrica',
  },
  'settings.factoryHold.bodyOn': {
    en: 'Pipeline worker and Director auto-enqueue are paused. Queued ideas stay in the queue; agents do not start or continue work until you resume.',
    ru: 'Воркер пайплайна и авто-постановка Director на паузе. Идеи в очереди сохраняются; агенты не запускаются и не продолжают работу, пока не снимете паузу.',
    es: 'El worker del pipeline y el auto-encolado del Director están en pausa. Las ideas en cola se conservan; los agentes no arrancan ni continúan hasta reanudar.',
  },
  'settings.factoryHold.bodyOff': {
    en: 'Factory is running. Pipeline tasks and scheduled Director products can proceed normally.',
    ru: 'Фабрика работает. Задачи пайплайна и продукты Director по расписанию выполняются как обычно.',
    es: 'La fábrica está activa. Las tareas del pipeline y los productos programados del Director siguen con normalidad.',
  },
  'settings.factoryHold.hint': {
    en: 'Saves automatically. Emergency override: AIFACTORY_FACTORY_ON_HOLD=1 in the app environment.',
    ru: 'Сохраняется автоматически. Аварийно: AIFACTORY_FACTORY_ON_HOLD=1 в окружении приложения.',
    es: 'Se guarda automáticamente. Anulación de emergencia: AIFACTORY_FACTORY_ON_HOLD=1 en el entorno de la app.',
  },
  'settings.factoryHold.whereToFind': {
    en: 'First block below: pause or resume the pipeline worker and Director auto-enqueue (factory hold).',
    ru: 'Первый блок ниже: пауза или запуск воркера пайплайна и авто-постановки Director (hold фабрики).',
    es: 'Primer bloque abajo: pausar o reanudar el worker del pipeline y el auto-encolado del Director.',
  },
  'settings.factoryHold.demoNote': {
    en: 'Works in public demo mode — the only Settings control that can be changed on the shared demo host.',
    ru: 'Работает в публичном демо — единственный переключатель в «Настройках», доступный на общем демо-хосте.',
    es: 'Funciona en demo público — el único control en Ajustes que se puede cambiar en el host demo compartido.',
  },
  'settings.factoryHold.globalBannerOn': {
    en: 'Factory is on hold — pipeline paused. Resume in Settings → Factory hold.',
    ru: 'Фабрика на паузе — пайплайн остановлен. Снять паузу: Настройки → Пауза фабрики.',
    es: 'Fábrica en pausa. Reanudar en Ajustes → Pausa de la fábrica.',
  },
  'settings.factoryHold.openSettings': {
    en: 'Open Settings',
    ru: 'Открыть настройки',
    es: 'Abrir ajustes',
  },
  'settings.factoryHold.labelOn': {
    en: 'ON HOLD',
    ru: 'ПАУЗА',
    es: 'EN PAUSA',
  },
  'settings.factoryHold.labelOff': {
    en: 'Running',
    ru: 'Работает',
    es: 'Activa',
  },
  'settings.factoryHold.ariaPause': {
    en: 'Put factory on hold',
    ru: 'Поставить фабрику на паузу',
    es: 'Pausar la fábrica',
  },
  'settings.factoryHold.ariaResume': {
    en: 'Resume factory',
    ru: 'Снять паузу с фабрики',
    es: 'Reanudar la fábrica',
  },
  'settings.toast.factoryHoldOn': {
    en: 'Factory on hold — pipeline paused',
    ru: 'Фабрика на паузе — пайплайн остановлен',
    es: 'Fábrica en pausa — pipeline detenido',
  },
  'settings.toast.factoryHoldOff': {
    en: 'Factory resumed',
    ru: 'Фабрика снова работает',
    es: 'Fábrica reanudada',
  },
};
