import type { I18nDict } from '../../types';

export const STANDUP_SETTINGS_DICT: I18nDict = {
  'settings.section.directorStandup': {
    en: 'Director standup — Corporate Chat',
    ru: 'Стендап Director — Corporate Chat',
    es: 'Standup del Director — Corporate Chat',
  },
  'settings.standup.intro': {
    en: 'AI Director runs a standup in Corporate Chat at the scheduled local time: plan, agent-style reports, clarifying questions. You participate as Owner (display name is configured in Corporate Chat tab). This differs from Brainstorming sessions — see docs/corporate-chat-vs-discussions.md.',
    ru: 'AI Director проводит стендап в Corporate Chat в запланированное локальное время: план, отчёты в стиле агентов, уточняющие вопросы. Вы участвуете как Owner (отображаемое имя задаётся во вкладке Corporate Chat). Это не Brainstorming — см. docs/corporate-chat-vs-discussions.md.',
    es: 'El AI Director hace un standup en Corporate Chat a la hora local programada: plan, informes estilo agente, preguntas aclaratorias. Participas como Owner (el nombre se configura en la pestaña Corporate Chat). No es lo mismo que Brainstorming — ver docs/corporate-chat-vs-discussions.md.',
  },
  'settings.standup.enableDaily': {
    en: 'Enable daily standup',
    ru: 'Включить ежедневный стендап',
    es: 'Activar standup diario',
  },
  'settings.standup.localTime': {
    en: 'Local time (HH:MM)',
    ru: 'Локальное время (ЧЧ:ММ)',
    es: 'Hora local (HH:MM)',
  },
  'settings.standup.timezone': {
    en: 'IANA timezone',
    ru: 'Часовой пояс IANA',
    es: 'Zona horaria IANA',
  },
  'settings.standup.saving': {
    en: 'Saving standup schedule…',
    ru: 'Сохранение расписания стендапа…',
    es: 'Guardando horario de standup…',
  },
  'settings.standup.autosaveHint': {
    en: 'Standup schedule saves automatically a moment after you change it.',
    ru: 'Расписание стендапа сохраняется автоматически через мгновение после изменения.',
    es: 'El horario del standup se guarda solo un momento después de cambiarlo.',
  },
  'settings.toast.standupSaved': {
    en: '✅ Corporate Chat / standup schedule saved',
    ru: '✅ Corporate Chat / расписание стендапа сохранено',
    es: '✅ Corporate Chat / horario de standup guardado',
  },
  'settings.toast.standupSaveFailed': {
    en: 'Failed to save standup schedule',
    ru: 'Не удалось сохранить расписание стендапа',
    es: 'Error al guardar el horario del standup',
  },
};
